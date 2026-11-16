from __future__ import annotations

from aggregator import RadarService
from db import Database, make_id
from sources import SourceSpec

HACKATHON = {
    "title": "Reliable Systems Hack",
    "url": "https://example.com/reliable",
    "platform": "Example",
}


class FakeNotifier:
    def __init__(self, *, succeeds: bool = True) -> None:
        self.succeeds = succeeds
        self.sent: list[dict] = []
        self.errors: list[tuple[str, Exception]] = []

    def send_hackathon(self, hackathon: dict) -> bool:
        self.sent.append(hackathon)
        return self.succeeds

    def send_error_message(self, source: str, error: Exception) -> bool:
        self.errors.append((source, error))
        return True


def test_baseline_marks_without_sending(settings_factory) -> None:
    settings = settings_factory(bootstrap_mode="baseline")
    database = Database(settings.database_path)
    database.init()
    notifier = FakeNotifier()
    source = SourceSpec("example", "Example", lambda: [HACKATHON])

    report = RadarService(settings, database, notifier, [source]).run_cycle()

    assert report.baselined == 1
    assert notifier.sent == []
    assert database.is_seen(make_id(HACKATHON["title"], HACKATHON["url"])) is True


def test_duplicate_is_sent_once(settings_factory) -> None:
    settings = settings_factory()
    database = Database(settings.database_path)
    database.init()
    notifier = FakeNotifier()
    source = SourceSpec("example", "Example", lambda: [HACKATHON, HACKATHON])
    service = RadarService(settings, database, notifier, [source])

    first = service.run_cycle()
    second = service.run_cycle()

    assert first.sent == 1
    assert second.sent == 0
    assert len(notifier.sent) == 1


def test_failed_delivery_is_not_marked_seen(settings_factory) -> None:
    settings = settings_factory()
    database = Database(settings.database_path)
    database.init()
    notifier = FakeNotifier(succeeds=False)
    source = SourceSpec("example", "Example", lambda: [HACKATHON])

    report = RadarService(settings, database, notifier, [source]).run_cycle()

    uid = make_id(HACKATHON["title"], HACKATHON["url"])
    assert report.delivery_failures == 1
    assert database.is_seen(uid) is False


def test_source_error_does_not_cancel_other_source(settings_factory) -> None:
    settings = settings_factory()
    database = Database(settings.database_path)
    database.init()
    notifier = FakeNotifier()

    def fail() -> list[dict]:
        raise RuntimeError("provider unavailable")

    sources = [
        SourceSpec("broken", "Broken", fail),
        SourceSpec("working", "Working", lambda: [HACKATHON]),
    ]
    report = RadarService(settings, database, notifier, sources).run_cycle()

    assert report.sent == 1
    assert report.source_errors == {"broken": "RuntimeError: provider unavailable"}


def test_notifier_exception_does_not_mark_seen(settings_factory) -> None:
    settings = settings_factory()
    database = Database(settings.database_path)
    database.init()

    class RaisingNotifier(FakeNotifier):
        def send_hackathon(self, hackathon: dict) -> bool:
            raise ValueError("bad message")

    source = SourceSpec("example", "Example", lambda: [HACKATHON])
    report = RadarService(settings, database, RaisingNotifier(), [source]).run_cycle()

    uid = make_id(HACKATHON["title"], HACKATHON["url"])
    assert report.delivery_failures == 1
    assert database.is_seen(uid) is False
