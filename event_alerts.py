from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from html import escape
from zoneinfo import ZoneInfo

from event_model import CanonicalEvent

WAT = ZoneInfo("Africa/Lagos")
TELEGRAM_MESSAGE_LIMIT = 4096

_HEADERS = {
    "new": "🆕 <b>New listing</b>",
    "ongoing": "🟢 <b>Open now</b>",
    "deadline": "⏰ <b>Deadline soon</b>",
    "deadline_soon": "⏰ <b>Deadline soon</b>",
    "change": "🔄 <b>Event updated</b>",
}

_CHANGE_LABELS = {
    "prize_pool_text": "Prize",
    "reg_deadline": "Registration",
    "submit_deadline": "Deadline",
    "status": "Status",
}


def format_event_alert(
    event: CanonicalEvent | dict[str, object],
    *,
    alert_type: str,
    reasons: tuple[str, ...] | list[str] = (),
    changes: dict[str, tuple[str, str]] | None = None,
) -> str:
    """Build a compact HTML alert for a canonical event."""
    lines = [
        _HEADERS.get(alert_type, _HEADERS["new"]),
        f"<b>{escape(str(event.get('title') or 'Untitled event'))}</b>",
    ]

    facts = _facts_line(event)
    if facts:
        lines.append(facts)

    tags = _tags_line(event)
    if tags:
        lines.append(tags)

    change_line = _change_line(changes or {})
    if change_line:
        lines.append(change_line)
    elif reasons:
        lines.append("Matched: " + " + ".join(escape(str(reason)) for reason in reasons))

    sources = _source_names(event)
    if sources:
        lines.append("Sources: " + " · ".join(escape(source) for source in sources))

    first_seen = _format_first_seen(str(event.get("listed_at") or ""))
    if first_seen:
        lines.append(f"First seen: {first_seen}")

    return "\n".join(lines)


def format_ongoing_digest(events: Sequence[CanonicalEvent]) -> str:
    rows: list[str] = []
    for index, event in enumerate(events, start=1):
        title = escape(_truncate_text(event["title"], 120))
        url = escape(event["canonical_url"], quote=True)
        details = [
            _format_day(event["submit_deadline"] or event["reg_deadline"]),
            _display_mode(event["mode"]),
        ]
        suffix = " · ".join(escape(item) for item in details if item)
        row = f'{index}. <a href="{url}">{title}</a>'
        row = f"{row} — {suffix}" if suffix else row
        candidate = _digest_lines((*rows, row))
        if len(candidate) > TELEGRAM_MESSAGE_LIMIT:
            break
        rows.append(row)
    return _digest_lines(rows)


def _digest_lines(rows: Sequence[str]) -> str:
    lines = [
        f"🟢 <b>Ongoing radar · {len(rows)}</b>",
        "Nearest deadlines first.",
        "",
        *rows,
    ]
    return "\n".join(lines)


def _facts_line(event: CanonicalEvent | dict[str, object]) -> str:
    facts = [
        _date_range(str(event.get("starts_at") or ""), str(event.get("ends_at") or "")),
        _display_mode(str(event.get("mode") or "")),
        str(event.get("prize_pool_text") or "").strip(),
    ]
    return " · ".join(escape(fact) for fact in facts if fact)


def _tags_line(event: CanonicalEvent | dict[str, object]) -> str:
    confidence = event.get("confidence") or {}
    confidence = confidence if isinstance(confidence, dict) else {}
    regions = _tag_values(event.get("regions"))
    stacks = _tag_values(event.get("stacks"))
    inferred = list(regions)
    verified: list[str] = []
    if confidence.get("stacks") == "verified":
        verified.extend(stacks)
    else:
        inferred.extend(stacks)
    parts = []
    if inferred:
        parts.append("Inferred: " + ", ".join(escape(value) for value in inferred))
    if verified:
        parts.append("Tags: " + ", ".join(escape(value) for value in verified))
    return " · ".join(parts)


def _tag_values(raw: object) -> list[str]:
    if not isinstance(raw, (list, tuple)):
        return []
    return list(dict.fromkeys(_display_tag(str(item)) for item in raw if item))


def _source_names(event: CanonicalEvent | dict[str, object]) -> list[str]:
    sources = event.get("sources") or []
    if not isinstance(sources, (list, tuple)):
        return []
    names = []
    for item in sources:
        if isinstance(item, dict) and item.get("platform"):
            names.append(str(item["platform"]))
    return list(dict.fromkeys(names))


def _change_line(changes: dict[str, tuple[str, str]]) -> str:
    if not changes:
        return ""
    field, values = next(iter(changes.items()))
    previous, current = values
    label = _CHANGE_LABELS.get(field, field.replace("_", " ").title())
    if "deadline" in field:
        previous = _format_day(previous)
        current = _format_day(current)
    elif field == "status":
        previous = _display_tag(previous)
        current = _display_tag(current)
    return f"{escape(label)}: {escape(previous or 'Unknown')} → {escape(current or 'Unknown')}"


def _date_range(start_text: str, end_text: str) -> str:
    start = _parse_date(start_text)
    end = _parse_date(end_text)
    if start and end:
        if start.year == end.year and start.month == end.month:
            return f"{start.day}–{end.day} {start.strftime('%b')}"
        if start.year == end.year:
            return f"{start.day} {start.strftime('%b')}–{end.day} {end.strftime('%b')}"
        return f"{start.day} {start.strftime('%b %Y')}–{end.day} {end.strftime('%b %Y')}"
    if start:
        return f"Starts {_format_day(start_text)}"
    if end:
        return f"Ends {_format_day(end_text)}"
    return ""


def _format_day(value: str) -> str:
    parsed = _parse_date(value)
    return f"{parsed.day} {parsed.strftime('%b')}" if parsed else value


def _format_first_seen(value: str) -> str:
    if not value:
        return ""
    try:
        observed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=WAT)
    local = observed.astimezone(WAT)
    return f"{local.day} {local.strftime('%b %H:%M')} WAT"


def _display_mode(value: str) -> str:
    return {
        "online": "Online",
        "in_person": "In person",
        "hybrid": "Hybrid",
        "unknown": "",
    }.get(value.casefold(), value)


def _display_tag(value: str) -> str:
    return value.replace("_", " ").title()


def _truncate_text(value: str, limit: int) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 1].rstrip()}…"


def _parse_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None
