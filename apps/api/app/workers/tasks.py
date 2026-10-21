import logging
from datetime import UTC, datetime

from app.workers.broker import broker

logger = logging.getLogger(__name__)


@broker.task(task_name="system.heartbeat", schedule=[{"cron": "*/5 * * * *"}])
async def heartbeat() -> str:
    """Proves the scheduler → broker → worker path works. Replace with real jobs in Phase 1."""
    now = datetime.now(UTC).isoformat()
    logger.info("worker heartbeat")
    return now
