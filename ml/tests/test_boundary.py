"""movie_ml stays a pure library (ADR-026): no API app, settings, DB or HTTP imports."""

import ast
from pathlib import Path

import movie_ml

PACKAGE_DIR = Path(movie_ml.__file__).parent
FORBIDDEN_ROOTS = frozenset(
    {"app", "alembic", "asyncpg", "fastapi", "httpx", "pydantic_settings", "redis", "sqlalchemy"}
)


def _imported_roots(source: str) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_package_ships_type_information() -> None:
    assert (PACKAGE_DIR / "py.typed").is_file()


def test_no_module_imports_app_or_infrastructure() -> None:
    offenders = {
        str(path.relative_to(PACKAGE_DIR)): sorted(bad)
        for path in PACKAGE_DIR.rglob("*.py")
        if (bad := _imported_roots(path.read_text(encoding="utf-8")) & FORBIDDEN_ROOTS)
    }
    assert offenders == {}


def test_detector_catches_forbidden_imports() -> None:
    source = "import sqlalchemy.orm\nfrom app.core import db\nfrom . import sibling\n"
    assert _imported_roots(source) & FORBIDDEN_ROOTS == {"app", "sqlalchemy"}
