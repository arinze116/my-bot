from __future__ import annotations

from datetime import UTC, datetime

from event_model import canonicalize_hackathon, events_match


def test_canonical_event_derives_status_tags_and_stable_id() -> None:
    now = datetime(2026, 11, 17, 9, tzinfo=UTC)
    raw = {
        "title": "Africa Solana AI Hack",
        "url": "https://example.com/register?utm_source=x",
        "platform": "X/Twitter",
        "prize": "$25,000",
        "start_date": "2026-11-20",
        "end_date": "2026-11-23",
        "deadline": "2026-11-19",
        "mode": "Online",
        "tech_tags": "Solana, AI",
        "eligibility": "Open to Africa",
    }

    event = canonicalize_hackathon(raw, now=now)
    renamed = canonicalize_hackathon({**raw, "deadline": "2026-11-21"}, now=now)

    assert event["event_id"] == renamed["event_id"]
    assert event["status"] == "open_submission"
    assert event["regions"] == ["africa"]
    assert event["stacks"] == ["ai", "solana"]
    assert event["prize_pool_usd"] == 25000
    assert event["canonical_url"] == "https://example.com/register"


def test_events_match_same_event_seen_by_listing_and_x() -> None:
    now = datetime(2026, 11, 17, tzinfo=UTC)
    listing = canonicalize_hackathon(
        {
            "title": "Lagos AI Buildathon 2026",
            "url": "https://events.example.org/lagos-ai",
            "platform": "Luma",
            "start_date": "2026-12-01",
            "end_date": "2026-12-03",
        },
        now=now,
    )
    social = canonicalize_hackathon(
        {
            "title": "Lagos AI Buildathon",
            "url": "https://events.example.org/lagos-ai?utm_campaign=launch",
            "platform": "X/Twitter",
            "start_date": "2026-12-01",
            "end_date": "2026-12-03",
        },
        now=now,
    )

    assert events_match(listing, social) is True
