from app.workers.broker import broker
from app.workers.scheduler import scheduler
from app.workers.tasks import heartbeat


async def test_heartbeat_runs_through_broker() -> None:
    task = await heartbeat.kiq()
    result = await task.wait_result(timeout=2)

    assert not result.is_err
    assert isinstance(result.return_value, str)


def test_heartbeat_is_scheduled() -> None:
    assert scheduler.broker is broker
    assert heartbeat.labels["schedule"] == [{"cron": "*/5 * * * *"}]
