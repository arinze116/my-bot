from __future__ import annotations

from datetime import UTC, datetime

from alert_planner import AlertPlanner, UserPreferences, event_matches_filters
from event_model import canonicalize_hackathon
from event_store import UpsertResult


def _event(**overrides: str):
    raw = {
        "title": "Africa Solana Builders Hack",
        "url": "https://example.com/africa-solana",
        "platform": "DoraHacks",
        "start_date": "2026-11-20",
        "end_date": "2026-11-23",
        "deadline": "2026-11-20",
        "mode": "Online",
        "tech_tags": "Solana, Web3",
        "eligibility": "Africa builders",
        "prize": "$5,000",
    }
    raw.update(overrides)
    return canonicalize_hackathon(raw, now=datetime(2026, 11, 17, tzinfo=UTC))


def test_filter_engine_explains_region_and_stack_match() -> None:
    event = _event()
    preferences = UserPreferences(regions=("africa",), stacks=("solana",))

    decision = event_matches_filters(event, preferences)

    assert decision.matches is True
    assert decision.reasons == ("Africa", "Solana")


def test_muted_source_never_passes_filters() -> None:
    event = _event()
    event["sources"] = [{"platform": "DoraHacks", "url": event["canonical_url"], "seen_at": ""}]
    preferences = UserPreferences(muted_sources=("dorahacks",))

    assert event_matches_filters(event, preferences).matches is False


def test_quiet_hours_queue_new_alert_until_0630_wat() -> None:
    now = datetime(2026, 11, 17, 1, 30, tzinfo=UTC)  # 02:30 WAT
    event = _event()
    planner = AlertPlanner(UserPreferences())

    plans = planner.plan_upsert(event, UpsertResult(event, is_new=True), now=now)

    assert len(plans) == 1
    assert plans[0].alert_type == "new"
    assert plans[0].deliver_at.isoformat() == "2026-11-17T05:30:00+00:00"


def test_deadline_plans_have_stable_72h_and_24h_keys() -> None:
    now = datetime(2026, 11, 17, 12, tzinfo=UTC)
    planner = AlertPlanner(UserPreferences(quiet_hours_enabled=False))
    at_72h = _event(deadline="2026-11-20")
    at_24h = _event(deadline="2026-11-18")

    first = planner.plan_deadline(at_72h, now=now)
    second = planner.plan_deadline(at_24h, now=now)

    assert first.alert_key == "deadline72:" + at_72h["event_id"]
    assert second.alert_key == "deadline24:" + at_24h["event_id"]


def test_material_change_plan_is_not_new_alert() -> None:
    event = _event(deadline="2026-11-22")
    result = UpsertResult(
        event,
        is_new=False,
        material_changes={"submit_deadline": ("2026-11-20", "2026-11-22")},
    )
    planner = AlertPlanner(UserPreferences(quiet_hours_enabled=False))

    plans = planner.plan_upsert(event, result, now=datetime(2026, 11, 17, 12, tzinfo=UTC))

    assert [plan.alert_type for plan in plans] == ["change"]
    assert plans[0].changes == result.material_changes
