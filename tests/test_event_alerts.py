from __future__ import annotations

from datetime import UTC, datetime

from event_alerts import format_event_alert
from event_model import canonicalize_hackathon


def _event():
    event = canonicalize_hackathon(
        {
            "title": "Africa <AI> Builders Hack",
            "url": "https://example.com/apply?track=ai&region=africa",
            "platform": "DoraHacks",
            "start_date": "2026-11-20",
            "end_date": "2026-11-23",
            "deadline": "2026-11-19",
            "mode": "Online",
            "tech_tags": "AI, Solana",
            "prize": "$5,000",
            "description": "Build and ship.",
        },
        now=datetime(2026, 11, 17, 12, tzinfo=UTC),
    )
    event["sources"].append(
        {
            "platform": "X/Twitter",
            "url": "https://example.com/apply",
            "seen_at": "2026-11-17T12:05:00+00:00",
        }
    )
    return event


def test_event_alert_is_compact_actionable_and_provenanced() -> None:
    text = format_event_alert(
        _event(),
        alert_type="new",
        reasons=("Africa", "Solana"),
        changes={},
    )

    assert text.startswith("🆕 <b>New listing</b>\n<b>Africa &lt;AI&gt; Builders Hack</b>")
    assert "20–23 Nov · Online · $5,000" in text
    assert "Inferred: Africa · Tags: Ai, Solana" in text
    assert "Matched: Africa + Solana" in text
    assert "Sources: DoraHacks · X/Twitter" in text
    assert "First seen: 17 Nov 13:00 WAT" in text
    assert len([line for line in text.splitlines() if line.strip()]) <= 7


def test_material_change_alert_shows_only_changed_field() -> None:
    text = format_event_alert(
        _event(),
        alert_type="change",
        reasons=(),
        changes={"submit_deadline": ("2026-11-19", "2026-11-21")},
    )

    assert "🔄 <b>Event updated</b>" in text
    assert "Deadline: 19 Nov → 21 Nov" in text


def test_deadline_alert_uses_deadline_header() -> None:
    text = format_event_alert(
        _event(),
        alert_type="deadline_soon",
        reasons=(),
        changes={},
    )

    assert text.startswith("⏰ <b>Deadline soon</b>")
