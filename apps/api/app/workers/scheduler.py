from taskiq import TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource

from app.workers.broker import broker

# Cron schedules are declared on tasks via `schedule=[{"cron": "..."}]` labels.
# Run exactly one scheduler process per environment, or jobs will be enqueued twice.
scheduler = TaskiqScheduler(broker=broker, sources=[LabelScheduleSource(broker)])
