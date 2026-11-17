from __future__ import annotations

from datetime import UTC, datetime

from event_model import canonicalize_hackathon
from event_store import EventStore, Sighting


def _event(**overrides: str):
    raw = {
        "title": "Signal Builders Hack",
        "url": "https://example.com/signal",
        "platform": "Devpost",
        "start_date": "2026-11-20",
        "end_date": "2026-11-24",
        "deadline": "2026-11-23",
        "mode": "Online",
        "tech_tags": "AI, Security",
    }
    raw.update(overrides)
    return canonicalize_hackathon(raw, now=datetime(2026, 11, 17, tzinfo=UTC))


def test_two_sources_create_one_event_and_one_new_alert(tmp_path) -> None:
    store = EventStore(tmp_path / "radar.db")
    store.init()
    event = _event()

    first = store.upsert_event(
        event,
        Sighting("Devpost", event["canonical_url"], "2026-11-17T08:00:00+00:00"),
    )
    second = store.upsert_event(
        event,
        Sighting("X/Twitter", event["canonical_url"], "2026-11-17T08:05:00+00:00"),
    )

    assert first.is_new is True
    assert second.is_new is False
    assert store.total_events() == 1
    assert [item["platform"] for item in store.get_event(event["event_id"])["sources"]] == [
        "Devpost",
        "X/Twitter",
    ]
    assert store.record_alert(event["event_id"], "new", "new:" + event["event_id"]) is True
    assert store.record_alert(event["event_id"], "new", "new:" + event["event_id"]) is False


def test_deadline_change_is_material_not_a_second_new_event(tmp_path) -> None:
    store = EventStore(tmp_path / "radar.db")
    store.init()
    original = _event()
    store.upsert_event(original, Sighting("Devpost", original["canonical_url"], "2026-11-17"))
    changed = _event(deadline="2026-11-25")

    result = store.upsert_event(
        changed,
        Sighting("Devpost", changed["canonical_url"], "2026-11-18"),
    )

    assert result.is_new is False
    assert result.material_changes == {"submit_deadline": ("2026-11-23", "2026-11-25")}
    assert store.total_events() == 1


def test_ongoing_query_excludes_upcoming_and_ended_events(tmp_path) -> None:
    store = EventStore(tmp_path / "radar.db")
    store.init()
    now = datetime(2026, 11, 17, 12, tzinfo=UTC)
    ongoing = canonicalize_hackathon(
        {
            "title": "Open Now",
            "url": "https://example.com/open",
            "platform": "Example",
            "start_date": "2026-11-16",
            "end_date": "2026-11-20",
            "deadline": "2026-11-19",
        },
        now=now,
    )
    upcoming = canonicalize_hackathon(
        {
            "title": "Later",
            "url": "https://example.com/later",
            "platform": "Example",
            "start_date": "2026-12-01",
            "end_date": "2026-12-03",
        },
        now=now,
    )
    ended = canonicalize_hackathon(
        {
            "title": "Ended",
            "url": "https://example.com/ended",
            "platform": "Example",
            "start_date": "2026-11-01",
            "end_date": "2026-11-03",
        },
        now=now,
    )
    for event in (ongoing, upcoming, ended):
        store.upsert_event(event, Sighting("Example", event["canonical_url"], now.isoformat()))

    assert [event["title"] for event in store.list_ongoing(now=now)] == ["Open Now"]


def test_source_health_warns_once_after_error_streak(tmp_path) -> None:
    store = EventStore(tmp_path / "radar.db")
    store.init()
    now = datetime(2026, 11, 17, 8, tzinfo=UTC)

    for _ in range(3):
        health = store.record_source_error("devpost", "HTTP 503", now=now)

    assert health["error_streak"] == 3
    assert store.should_warn_source("devpost", threshold=3, now=now) is True
    store.mark_source_warned("devpost", now=now)
    assert store.should_warn_source("devpost", threshold=3, now=now) is False
    store.record_source_success("devpost", event_count=12, now=now)
    assert store.list_source_health()[0]["error_streak"] == 0


def test_preferences_queue_and_owner_actions_persist(tmp_path) -> None:
    store = EventStore(tmp_path / "radar.db")
    store.init()
    event = _event()
    store.upsert_event(event, Sighting("Devpost", event["canonical_url"], "2026-11-17"))
    store.save_preferences({"paused": True, "regions": ["africa"]})
    store.queue_alert(
        alert_key="new:" + event["event_id"],
        event_id=event["event_id"],
        alert_type="new",
        deliver_at="2026-11-17T05:30:00+00:00",
        payload={"reasons": ["Africa"]},
    )
    store.mark_interested(event["event_id"])
    store.mute_event(event["event_id"])

    due = store.list_due_alerts(now=datetime(2026, 11, 17, 6, tzinfo=UTC))

    assert store.load_preferences() == {"paused": True, "regions": ["africa"]}
    assert due[0]["payload"] == {"reasons": ["Africa"]}
    assert store.get_event_state(event["event_id"]) == {"interested": True, "muted": True}
    store.remove_queued_alert(due[0]["alert_key"])
    assert store.list_due_alerts(now=datetime(2026, 11, 17, 6, tzinfo=UTC)) == []


def test_bookmarks_can_be_added_listed_removed_and_reloaded(tmp_path) -> None:
    database_path = tmp_path / "radar.db"
    store = EventStore(database_path)
    store.init()
    event = _event()
    store.upsert_event(event, Sighting("Devpost", event["canonical_url"], "2026-11-17"))

    found = store.find_event(event["event_id"][:8])
    assert found is not None
    assert store.set_bookmarked(found["event_id"], bookmarked=True) is True

    reloaded = EventStore(database_path)
    assert [item["title"] for item in reloaded.list_bookmarks()] == ["Signal Builders Hack"]
    assert reloaded.find_event(event["canonical_url"])["event_id"] == event["event_id"]
    assert reloaded.set_bookmarked(event["event_id"], bookmarked=False) is True
    assert reloaded.list_bookmarks() == []


def test_new_and_soon_queries_are_ordered_for_commands(tmp_path) -> None:
    store = EventStore(tmp_path / "radar.db")
    store.init()
    now = datetime(2026, 11, 17, 12, tzinfo=UTC)
    soon = canonicalize_hackathon(
        {
            "title": "Deadline Tomorrow",
            "url": "https://example.com/tomorrow",
            "platform": "Example",
            "deadline": "2026-11-18",
        },
        now=now,
    )
    later = canonicalize_hackathon(
        {
            "title": "Deadline Later",
            "url": "https://example.com/later-deadline",
            "platform": "Example",
            "deadline": "2026-11-25",
        },
        now=now,
    )
    for event in (later, soon):
        store.upsert_event(event, Sighting("Example", event["canonical_url"], now.isoformat()))

    assert [item["title"] for item in store.list_new(limit=2)] == [
        "Deadline Tomorrow",
        "Deadline Later",
    ]
    assert [item["title"] for item in store.list_soon(now=now, hours=72)] == [
        "Deadline Tomorrow"
    ]
