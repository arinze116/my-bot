from __future__ import annotations

from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler

from aggregator import RadarService


def create_scheduler(service: RadarService, interval_minutes: int) -> BlockingScheduler:
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        service.run_cycle,
        trigger="interval",
        minutes=interval_minutes,
        next_run_time=datetime.now(scheduler.timezone),
        id="hackathon-radar-poll",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=max(60, interval_minutes * 60),
    )
    return scheduler


def run_scheduler(service: RadarService, interval_minutes: int) -> None:
    create_scheduler(service, interval_minutes).start()
