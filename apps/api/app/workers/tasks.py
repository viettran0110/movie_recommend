import logging
from datetime import UTC, datetime
from typing import Any

from app.core.config import get_settings
from app.modules.catalog.service import run_import
from app.workers.broker import broker

logger = logging.getLogger(__name__)


@broker.task(task_name="catalog.import")
async def import_catalog() -> dict[str, Any]:
    """On-demand CSV catalog import (ADR-023). Not scheduled: run it when data/ changes.

    Reindexing the changed titles is wired in once Meilisearch indexing exists.
    """
    report = await run_import(get_settings())
    return report.model_dump(mode="json")


@broker.task(task_name="system.heartbeat", schedule=[{"cron": "*/5 * * * *"}])
async def heartbeat() -> str:
    """Proves the scheduler → broker → worker path works. Replace with real jobs in Phase 1."""
    now = datetime.now(UTC).isoformat()
    logger.info("worker heartbeat")
    return now
