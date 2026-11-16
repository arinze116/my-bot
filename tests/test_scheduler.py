from __future__ import annotations

from scheduler import create_scheduler


class FakeService:
    def run_cycle(self) -> None:
        return None


def test_scheduler_allows_only_one_cycle_at_a_time() -> None:
    scheduler = create_scheduler(FakeService(), 20)
    job = scheduler.get_job("hackathon-radar-poll")

    assert job is not None
    assert job.max_instances == 1
    assert job.coalesce is True
