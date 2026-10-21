"""Taskiq broker (ADR-021). Run with:

taskiq worker app.workers.broker:broker app.workers.tasks
taskiq scheduler app.workers.scheduler:scheduler app.workers.tasks
"""

from taskiq import AsyncBroker, InMemoryBroker
from taskiq_redis import RedisStreamBroker

from app.core.config import get_settings


def create_broker() -> AsyncBroker:
    settings = get_settings()
    if settings.app_env == "test":
        return InMemoryBroker()
    # Stream broker: messages are acknowledged after execution and re-delivered if a worker
    # dies (idle_timeout). Its 2 s XREADGROUP block stays below redis-py 8's default 5 s
    # socket timeout; ListQueueBroker's unbounded BRPOP crashes workers on that timeout.
    return RedisStreamBroker(
        url=settings.redis_url,
        queue_name="movie:tasks",
        consumer_group_name="movie-workers",
        maxlen=10_000,
    )


broker = create_broker()
