"""Tmdb5000CsvSource against the small fixture CSVs in tests/fixtures/tmdb5000/."""

import shutil
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.modules.catalog.schemas import CatalogRecord, InvalidRecord
from app.modules.catalog.slugs import slugify
from app.modules.catalog.sources.tmdb5000_csv import (
    CREDITS_FILE,
    MOVIES_FILE,
    Tmdb5000CsvSource,
)
from app.modules.titles.models import CreditRole, MediaType, TitleStatus
from app.workers.tasks import import_catalog

FIXTURES = Path(__file__).parent / "fixtures" / "tmdb5000"


@pytest.fixture(scope="module")
def items() -> list[CatalogRecord | InvalidRecord]:
    return list(Tmdb5000CsvSource(FIXTURES).read())


def records(items: list[CatalogRecord | InvalidRecord]) -> dict[int, CatalogRecord]:
    return {i.title.tmdb_id: i for i in items if isinstance(i, CatalogRecord)}


def invalid(items: list[CatalogRecord | InvalidRecord]) -> list[InvalidRecord]:
    return [i for i in items if isinstance(i, InvalidRecord)]


def test_valid_and_invalid_rows_are_separated(
    items: list[CatalogRecord | InvalidRecord],
) -> None:
    assert sorted(records(items)) == [100, 200, 400]
    errors = {i.source_id: i.error for i in invalid(items)}
    assert set(errors) == {"300", "100", "abc"}
    assert errors["100"] == "duplicate id"
    assert errors["300"].startswith("genres:")
    assert errors["abc"].startswith("id:")


def test_errors_do_not_echo_cell_contents(items: list[CatalogRecord | InvalidRecord]) -> None:
    for item in invalid(items):
        assert "{not json" not in item.error
        assert "Bad Id" not in item.error


def test_full_row_maps_to_record(items: list[CatalogRecord | InvalidRecord]) -> None:
    record = records(items)[100]
    title = record.title

    assert title.media_type is MediaType.MOVIE
    assert (title.title, title.original_title) == ("Alpha Movie", "Alpha Movie")
    assert title.release_date == date(2001, 2, 3)
    assert title.status is TitleStatus.RELEASED
    assert title.tmdb_vote_avg == Decimal("7.2")
    assert (title.tmdb_popularity, title.tmdb_vote_count) == (12.5, 150)
    assert record.details is not None
    assert (record.details.runtime, record.details.budget, record.details.revenue) == (
        120,
        1_000_000,
        5_000_000,
    )
    assert [g.name for g in record.genres] == ["Action", "Drama"]
    assert [k.tmdb_id for k in record.keywords] == [1, 2]


def test_credits_keep_all_cast_and_selected_crew(
    items: list[CatalogRecord | InvalidRecord],
) -> None:
    credits = records(items)[100].credits

    cast = [c for c in credits if c.role is CreditRole.CAST]
    crew = [c for c in credits if c.role is CreditRole.CREW]
    assert [(c.person_name, c.character, c.sort_order) for c in cast] == [
        ("Ann Actor", "Hero", 0),
        ("Bob Actor", None, 1),  # blank character -> None
    ]
    # "Sound Editor" is not a kept crew job.
    assert [(c.person_name, c.job) for c in crew] == [("Dee Director", "Director")]


def test_unknown_values_become_none(items: list[CatalogRecord | InvalidRecord]) -> None:
    record = records(items)[200]

    assert record.title.release_date is None
    assert record.title.overview is None
    assert record.title.tagline is None
    assert record.title.original_title == "Beta: The Sequel"  # falls back to title
    assert record.title.status is TitleStatus.POST_PRODUCTION
    assert record.details is not None
    assert (record.details.runtime, record.details.budget, record.details.revenue) == (
        None,
        None,
        None,
    )


def test_invalid_nested_item_is_dropped_not_the_title(
    items: list[CatalogRecord | InvalidRecord],
) -> None:
    # Keyword 3's name is a lone non-breaking space.
    assert [k.tmdb_id for k in records(items)[200].keywords] == [2]


def test_title_without_credits_row_is_kept(items: list[CatalogRecord | InvalidRecord]) -> None:
    record = records(items)[400]

    assert record.credits == ()
    assert record.title.title == "Crème Brûlée"


def test_missing_column_fails_the_whole_source(tmp_path: Path) -> None:
    shutil.copy(FIXTURES / CREDITS_FILE, tmp_path / CREDITS_FILE)
    lines = (FIXTURES / MOVIES_FILE).read_text(encoding="utf-8").splitlines()
    header = lines[0].replace(",vote_count", "")
    (tmp_path / MOVIES_FILE).write_text("\n".join([header, *lines[1:]]), encoding="utf-8")

    with pytest.raises(ValueError, match="vote_count"):
        list(Tmdb5000CsvSource(tmp_path).read())


def test_missing_file_fails_the_whole_source(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        list(Tmdb5000CsvSource(tmp_path).read())


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Alpha Movie", "alpha-movie"),
        ("Beta: The Sequel", "beta-the-sequel"),
        ("Crème Brûlée", "creme-brulee"),
        ("  --Weird__Spacing!!  ", "weird-spacing"),
        ("千と千尋の神隠し", "untitled"),
        ("x" * 100, "x" * 80),
    ],
)
def test_slugify(value: str, expected: str) -> None:
    assert slugify(value) == expected


def test_import_task_is_registered_and_not_scheduled() -> None:
    assert import_catalog.task_name == "catalog.import"
    assert "schedule" not in import_catalog.labels
