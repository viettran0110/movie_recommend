"""Catalog sources (ADR-023). The importer depends only on this protocol, so a TMDB API
source or a source for another media type plugs in without changing tables or upserts."""

from collections.abc import Iterator
from typing import Protocol

from app.modules.catalog.schemas import CatalogRecord, InvalidRecord


class CatalogSource(Protocol):
    @property
    def name(self) -> str:
        """Stable identifier, used in logs and the import report."""
        ...

    def read(self) -> Iterator[CatalogRecord | InvalidRecord]:
        """Yield one item per source title. Blocking I/O is fine: the importer runs this
        in a thread. Raise only for whole-source failures (missing file, wrong columns)."""
        ...
