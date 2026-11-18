from __future__ import annotations

from datetime import UTC, datetime

from aggregator import RadarService
from alert_planner import AlertPlanner, UserPreferences
from db import Database, make_id
from event_model import canonicalize_hackathon
from event_store import EventStore, Sighting
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


class EventNotifier(FakeNotifier):
    def __init__(self, *, succeeds: bool = True) -> None:
        super().__init__(succeeds=succeeds)
        self.event_alerts: list[tuple[str, str]] = []
        self.health_alerts: list[str] = []
        self.digests: list[list[str]] = []

    def send_event(self, event: dict, *, alert_type: str, reasons=(), changes=None) -> bool:
        self.event_alerts.append((event["event_id"], alert_type))
        return self.succeeds

    def send_source_health(self, source: str, error_streak: int, error: str) -> bool:
        self.health_alerts.append(source)
        return True

    def send_digest(self, events: list[dict]) -> bool:
        self.digests.append([event["event_id"] for event in events])
        return self.succeeds


class FakeVerifier:
    def __init__(self, result: bool = True) -> None:
        self.result = result

    def is_resolvable(self, url: str) -> bool:
        return self.result


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


def test_cross_source_event_sends_one_new_alert(settings_factory) -> None:
    settings = settings_factory(bootstrap_mode="notify")
    database = Database(settings.database_path)
    database.init()
    store = EventStore(settings.database_path)
    store.init()
    notifier = EventNotifier()
    event = {
        **HACKATHON,
        "start_date": "2026-12-01",
        "end_date": "2026-12-03",
        "deadline": "2026-11-30",
    }
    sources = [
        SourceSpec("listing", "Listing", lambda: [{**event, "platform": "Devpost"}]),
        SourceSpec("social", "Social", lambda: [{**event, "platform": "X/Twitter"}]),
    ]
    service = RadarService(
        settings,
        database,
        notifier,
        sources,
        event_store=store,
        planner=AlertPlanner(UserPreferences(quiet_hours_enabled=False)),
        url_verifier=FakeVerifier(),
        clock=lambda: datetime(2026, 11, 17, 12, tzinfo=UTC),
    )

    report = service.run_cycle()

    assert report.sent == 1
    assert [alert_type for _, alert_type in notifier.event_alerts] == ["new"]
    assert store.total_events() == 1
    assert len(store.list_new(limit=1)[0]["sources"]) == 2


def test_quiet_hours_queue_instead_of_sending(settings_factory) -> None:
    settings = settings_factory(bootstrap_mode="notify")
    database = Database(settings.database_path)
    database.init()
    store = EventStore(settings.database_path)
    store.init()
    notifier = EventNotifier()
    service = RadarService(
        settings,
        database,
        notifier,
        [SourceSpec("example", "Example", lambda: [HACKATHON])],
        event_store=store,
        planner=AlertPlanner(UserPreferences()),
        url_verifier=FakeVerifier(),
        clock=lambda: datetime(2026, 11, 17, 1, 30, tzinfo=UTC),
    )

    report = service.run_cycle()

    assert report.sent == 0
    assert report.queued == 1
    assert notifier.event_alerts == []
    assert len(store.list_due_alerts(now=datetime(2026, 11, 17, 6, tzinfo=UTC))) == 1


def test_dead_url_is_suppressed_before_alert(settings_factory) -> None:
    settings = settings_factory(bootstrap_mode="notify")
    database = Database(settings.database_path)
    database.init()
    store = EventStore(settings.database_path)
    store.init()
    notifier = EventNotifier()
    service = RadarService(
        settings,
        database,
        notifier,
        [SourceSpec("example", "Example", lambda: [HACKATHON])],
        event_store=store,
        planner=AlertPlanner(UserPreferences(quiet_hours_enabled=False)),
        url_verifier=FakeVerifier(False),
        clock=lambda: datetime(2026, 11, 17, 12, tzinfo=UTC),
    )

    report = service.run_cycle()

    assert report.sent == 0
    assert report.suppressed == 1
    assert notifier.event_alerts == []


def test_saved_pause_preference_is_reloaded_before_each_cycle(settings_factory) -> None:
    settings = settings_factory(bootstrap_mode="notify")
    database = Database(settings.database_path)
    database.init()
    store = EventStore(settings.database_path)
    store.init()
    store.save_preferences({"paused": True})
    notifier = EventNotifier()
    service = RadarService(
        settings,
        database,
        notifier,
        [SourceSpec("example", "Example", lambda: [HACKATHON])],
        event_store=store,
        planner=AlertPlanner(UserPreferences(quiet_hours_enabled=False)),
        url_verifier=FakeVerifier(),
        clock=lambda: datetime(2026, 11, 17, 12, tzinfo=UTC),
    )

    report = service.run_cycle()

    assert report.sent == 0
    assert notifier.event_alerts == []


def test_ongoing_digest_is_sent_once_per_wat_day(settings_factory) -> None:
    settings = settings_factory(bootstrap_mode="notify")
    database = Database(settings.database_path)
    database.init()
    store = EventStore(settings.database_path)
    store.init()
    now = datetime(2026, 11, 17, 6, tzinfo=UTC)  # 07:00 WAT
    event = canonicalize_hackathon(
        {
            "title": "Open Builders Week",
            "url": "https://example.com/open-builders",
            "platform": "Example",
            "start_date": "2026-11-16",
            "end_date": "2026-11-30",
            "deadline": "2026-11-25",
        },
        now=now,
    )
    store.upsert_event(event, Sighting("Example", event["canonical_url"], now.isoformat()))
    notifier = EventNotifier()
    service = RadarService(
        settings,
        database,
        notifier,
        [],
        event_store=store,
        planner=AlertPlanner(UserPreferences()),
        url_verifier=FakeVerifier(),
        clock=lambda: now,
    )

    first = service.run_cycle()
    second = service.run_cycle()

    assert first.sent == 1
    assert second.sent == 0
    assert notifier.digests == [[event["event_id"]]]


def test_new_ongoing_event_is_not_repeated_in_same_day_digest(settings_factory) -> None:
    settings = settings_factory(bootstrap_mode="notify")
    database = Database(settings.database_path)
    database.init()
    store = EventStore(settings.database_path)
    store.init()
    now = datetime(2026, 11, 17, 12, tzinfo=UTC)
    raw = {
        "title": "Live Builders Week",
        "url": "https://example.com/live-builders",
        "platform": "Example",
        "start_date": "2026-11-16",
        "end_date": "2026-11-30",
        "deadline": "2026-11-25",
    }
    notifier = EventNotifier()
    service = RadarService(
        settings,
        database,
        notifier,
        [SourceSpec("example", "Example", lambda: [raw])],
        event_store=store,
        planner=AlertPlanner(UserPreferences(quiet_hours_enabled=False)),
        url_verifier=FakeVerifier(),
        clock=lambda: now,
    )

    report = service.run_cycle()

    assert report.sent == 1
    assert [alert_type for _, alert_type in notifier.event_alerts] == ["new"]
    assert notifier.digests == []


def test_canonical_delivery_exception_is_isolated_and_not_recorded(settings_factory) -> None:
    settings = settings_factory(bootstrap_mode="notify")
    database = Database(settings.database_path)
    database.init()
    store = EventStore(settings.database_path)
    store.init()

    class RaisingEventNotifier(EventNotifier):
        def send_event(self, event: dict, *, alert_type: str, reasons=(), changes=None) -> bool:
            raise ValueError("bad canonical message")

    service = RadarService(
        settings,
        database,
        RaisingEventNotifier(),
        [SourceSpec("example", "Example", lambda: [HACKATHON])],
        event_store=store,
        planner=AlertPlanner(UserPreferences(quiet_hours_enabled=False, digest_enabled=False)),
        url_verifier=FakeVerifier(),
        clock=lambda: datetime(2026, 11, 17, 12, tzinfo=UTC),
    )

    report = service.run_cycle()

    event = store.list_new(limit=1)[0]
    assert report.delivery_failures == 1
    assert store.has_alert("new:" + event["event_id"]) is False


def test_new_event_is_not_repeated_as_deadline_alert_same_cycle(settings_factory) -> None:
    settings = settings_factory(bootstrap_mode="notify")
    database = Database(settings.database_path)
    database.init()
    store = EventStore(settings.database_path)
    store.init()
    notifier = EventNotifier()
    raw = {
        **HACKATHON,
        "deadline": "2026-11-18",
    }
    service = RadarService(
        settings,
        database,
        notifier,
        [SourceSpec("example", "Example", lambda: [raw])],
        event_store=store,
        planner=AlertPlanner(UserPreferences(quiet_hours_enabled=False, digest_enabled=False)),
        url_verifier=FakeVerifier(),
        clock=lambda: datetime(2026, 11, 17, 12, tzinfo=UTC),
    )

    report = service.run_cycle()

    assert report.sent == 1
    assert [alert_type for _, alert_type in notifier.event_alerts] == ["new"]


def test_due_deadline_queue_is_discarded_after_recent_new_alert(settings_factory) -> None:
    settings = settings_factory(bootstrap_mode="notify")
    database = Database(settings.database_path)
    database.init()
    store = EventStore(settings.database_path)
    store.init()
    now = datetime(2026, 11, 17, 6, tzinfo=UTC)
    event = canonicalize_hackathon(
        {
            **HACKATHON,
            "deadline": "2026-11-18",
        },
        now=now,
    )
    store.upsert_event(event, Sighting("Example", event["canonical_url"], now.isoformat()))
    store.record_alert(event["event_id"], "new", "new:" + event["event_id"])
    store.queue_alert(
        alert_key="deadline24:" + event["event_id"],
        event_id=event["event_id"],
        alert_type="deadline_soon",
        deliver_at="2026-11-17T05:30:00+00:00",
        payload={},
    )
    notifier = EventNotifier()
    service = RadarService(
        settings,
        database,
        notifier,
        [],
        event_store=store,
        planner=AlertPlanner(UserPreferences()),
        url_verifier=FakeVerifier(),
        clock=lambda: now,
    )

    report = service.run_cycle()

    assert report.sent == 0
    assert notifier.event_alerts == []
    assert store.list_due_alerts(now=now) == []


def test_due_queue_is_discarded_after_event_is_muted(settings_factory) -> None:
    settings = settings_factory(bootstrap_mode="notify")
    database = Database(settings.database_path)
    database.init()
    store = EventStore(settings.database_path)
    store.init()
    now = datetime(2026, 11, 17, 6, tzinfo=UTC)
    event = canonicalize_hackathon(HACKATHON, now=now)
    store.upsert_event(event, Sighting("Example", event["canonical_url"], now.isoformat()))
    store.queue_alert(
        alert_key="new:" + event["event_id"],
        event_id=event["event_id"],
        alert_type="new",
        deliver_at="2026-11-17T05:30:00+00:00",
        payload={},
    )
    store.mute_event(event["event_id"])
    notifier = EventNotifier()
    service = RadarService(
        settings,
        database,
        notifier,
        [],
        event_store=store,
        planner=AlertPlanner(UserPreferences(quiet_hours_enabled=False, digest_enabled=False)),
        url_verifier=FakeVerifier(),
        clock=lambda: now,
    )

    report = service.run_cycle()

    assert report.sent == 0
    assert report.suppressed == 1
    assert notifier.event_alerts == []
    assert store.list_due_alerts(now=now) == []


def test_unexpected_empty_source_counts_as_degraded_health(settings_factory) -> None:
    settings = settings_factory(bootstrap_mode="notify")
    database = Database(settings.database_path)
    database.init()
    store = EventStore(settings.database_path)
    store.init()
    notifier = EventNotifier()
    service = RadarService(
        settings,
        database,
        notifier,
        [SourceSpec("catalog", "Catalog", lambda: [])],
        event_store=store,
        planner=AlertPlanner(UserPreferences(digest_enabled=False)),
        url_verifier=FakeVerifier(),
        clock=lambda: datetime(2026, 11, 17, 12, tzinfo=UTC),
    )

    for _ in range(3):
        service.run_cycle()

    health = store.get_source_health("catalog")
    assert health["error_streak"] == 3
    assert health["event_count"] == 0
    assert notifier.health_alerts == ["Catalog"]
    assert database.is_source_initialized("catalog") is False


def test_explicitly_valid_empty_source_remains_healthy(settings_factory) -> None:
    settings = settings_factory(bootstrap_mode="notify")
    database = Database(settings.database_path)
    database.init()
    store = EventStore(settings.database_path)
    store.init()
    service = RadarService(
        settings,
        database,
        EventNotifier(),
        [SourceSpec("optional", "Optional", lambda: [], empty_result_is_valid=True)],
        event_store=store,
        planner=AlertPlanner(UserPreferences(digest_enabled=False)),
        url_verifier=FakeVerifier(),
        clock=lambda: datetime(2026, 11, 17, 12, tzinfo=UTC),
    )

    service.run_cycle()

    health = store.get_source_health("optional")
    assert health["error_streak"] == 0
    assert database.is_source_initialized("optional") is True


def test_cycle_status_records_successful_poll(settings_factory) -> None:
    settings = settings_factory(bootstrap_mode="notify")
    database = Database(settings.database_path)
    database.init()
    store = EventStore(settings.database_path)
    store.init()
    now = datetime(2026, 11, 17, 12, tzinfo=UTC)
    service = RadarService(
        settings,
        database,
        EventNotifier(),
        [SourceSpec("example", "Example", lambda: [HACKATHON])],
        event_store=store,
        planner=AlertPlanner(UserPreferences(quiet_hours_enabled=False, digest_enabled=False)),
        url_verifier=FakeVerifier(),
        clock=lambda: now,
    )

    service.run_cycle()

    status = store.get_runtime_status()
    assert status.outcome == "success"
    assert status.started_at == now.isoformat()
    assert status.completed_at == now.isoformat()
    assert status.fetched == 1
    assert status.source_errors == 0
    assert status.delivery_failures == 0
