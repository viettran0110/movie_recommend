"""Taskiq broker (ADR-021). Run with:

taskiq worker app.workers.broker:broker app.workers.tasks
taskiq scheduler app.workers.scheduler:scheduler app.workers.tasks
"""

from taskiq import AsyncBroker, InMemoryBroker
from taskiq_redis import ListQueueBroker

from app.core.config import get_settings


def create_broker() -> AsyncBroker:
    settings = get_settings()
    if settings.app_env == "test":
        return InMemoryBroker()
    return ListQueueBroker(url=settings.redis_url, queue_name="movie:tasks")


broker = create_broker()
