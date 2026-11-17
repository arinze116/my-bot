from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from event_model import MATERIAL_FIELDS, CanonicalEvent, events_match


@dataclass(frozen=True, slots=True)
class Sighting:
    platform: str
    url: str
    seen_at: str
    raw_ref: str = ""


@dataclass(frozen=True, slots=True)
class UpsertResult:
    event: CanonicalEvent
    is_new: bool
    material_changes: dict[str, tuple[str, str]] = field(default_factory=dict)


class EventStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA)
            connection.execute(
                "INSERT OR IGNORE INTO user_prefs (id, prefs_json) VALUES (1, '{}')"
            )

    def upsert_event(self, event: CanonicalEvent, sighting: Sighting) -> UpsertResult:
        with self._connect() as connection:
            existing_id = self._find_matching_event(connection, event)
            if existing_id is None:
                self._insert_event(connection, event)
                self._insert_sighting(connection, event["event_id"], sighting)
                return UpsertResult(
                    self._get_event(connection, event["event_id"]),
                    is_new=True,
                )
            existing = self._get_event(connection, existing_id)
            changes = _material_changes(existing, event)
            merged = _merge_event(existing, event)
            self._update_event(connection, existing_id, merged)
            self._insert_sighting(connection, existing_id, sighting)
        return UpsertResult(self.get_event(existing_id), is_new=False, material_changes=changes)

    def get_event(self, event_id: str) -> CanonicalEvent:
        with self._connect() as connection:
            return self._get_event(connection, event_id)

    def find_event(self, reference: str) -> CanonicalEvent | None:
        target = reference.strip()
        if not target:
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT event_id FROM events WHERE event_id = ? OR canonical_url = ? LIMIT 1",
                (target, target),
            ).fetchone()
            if row is None and _is_event_id_prefix(target):
                matches = connection.execute(
                    "SELECT event_id FROM events WHERE event_id LIKE ? LIMIT 2",
                    (f"{target}%",),
                ).fetchall()
                row = matches[0] if len(matches) == 1 else None
            return self._get_event(connection, str(row[0])) if row else None

    def total_events(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) FROM events").fetchone()
        return int(row[0])

    def record_alert(self, event_id: str, alert_type: str, alert_key: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO alerts_sent (alert_key, event_id, alert_type) "
                "VALUES (?, ?, ?)",
                (alert_key, event_id, alert_type),
            )
        return cursor.rowcount == 1

    def has_alert(self, alert_key: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM alerts_sent WHERE alert_key = ?", (alert_key,)
            ).fetchone()
        return row is not None

    def was_recently_alerted(
        self,
        event_id: str,
        *,
        since: datetime,
    ) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM alerts_sent WHERE event_id = ? "
                "AND alert_type IN ('new', 'change') "
                "AND datetime(sent_at) >= datetime(?) LIMIT 1",
                (event_id, _timestamp(since)),
            ).fetchone()
        return row is not None

    def list_ongoing(self, *, now: datetime, limit: int = 20) -> list[CanonicalEvent]:
        today = now.astimezone(UTC).date().isoformat()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT event_id FROM events WHERE status IN "
                "('open_registration', 'open_submission', 'ongoing') "
                "AND (ends_at = '' OR ends_at >= ?) AND muted = 0 "
                "ORDER BY COALESCE(NULLIF(submit_deadline, ''), '9999-12-31'), title LIMIT ?",
                (today, max(1, min(limit, 100))),
            ).fetchall()
            return [self._get_event(connection, str(row[0])) for row in rows]

    def list_new(self, *, limit: int = 10) -> list[CanonicalEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT event_id FROM events WHERE muted = 0 "
                "ORDER BY first_seen_at DESC, rowid DESC LIMIT ?",
                (max(1, min(limit, 100)),),
            ).fetchall()
            return [self._get_event(connection, str(row[0])) for row in rows]

    def list_bookmarks(self, *, limit: int = 20) -> list[CanonicalEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT event_id FROM events WHERE interested = 1 "
                "ORDER BY last_seen_at DESC, rowid DESC LIMIT ?",
                (max(1, min(limit, 100)),),
            ).fetchall()
            return [self._get_event(connection, str(row[0])) for row in rows]

    def list_soon(
        self, *, now: datetime, hours: int = 72, limit: int = 20
    ) -> list[CanonicalEvent]:
        current = now.astimezone(UTC) if now.tzinfo else now.replace(tzinfo=UTC)
        cutoff = current + timedelta(hours=hours)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT event_id FROM events WHERE muted = 0 AND "
                "(reg_deadline != '' OR submit_deadline != '')"
            ).fetchall()
            events = [self._get_event(connection, str(row[0])) for row in rows]
        due = [event for event in events if _is_due_within(event, current, cutoff)]
        due.sort(key=_deadline_sort_key)
        return due[: max(1, min(limit, 100))]

    def save_preferences(self, preferences: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE user_prefs SET prefs_json = ? WHERE id = 1",
                (json.dumps(preferences, sort_keys=True),),
            )

    def load_preferences(self) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT prefs_json FROM user_prefs WHERE id = 1").fetchone()
        return dict(json.loads(str(row[0]))) if row else {}

    def queue_alert(
        self,
        *,
        alert_key: str,
        event_id: str,
        alert_type: str,
        deliver_at: str,
        payload: dict[str, Any],
    ) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO queued_alerts "
                "(alert_key, event_id, alert_type, deliver_at, payload_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (alert_key, event_id, alert_type, deliver_at, json.dumps(payload, sort_keys=True)),
            )
        return cursor.rowcount == 1

    def list_due_alerts(self, *, now: datetime) -> list[dict[str, Any]]:
        timestamp = _timestamp(now)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT alert_key, event_id, alert_type, deliver_at, payload_json "
                "FROM queued_alerts WHERE deliver_at <= ? ORDER BY deliver_at, alert_key",
                (timestamp,),
            ).fetchall()
        return [
            {
                "alert_key": str(row[0]),
                "event_id": str(row[1]),
                "alert_type": str(row[2]),
                "deliver_at": str(row[3]),
                "payload": dict(json.loads(str(row[4]))),
            }
            for row in rows
        ]

    def remove_queued_alert(self, alert_key: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM queued_alerts WHERE alert_key = ?", (alert_key,))

    def mark_interested(self, event_id: str) -> None:
        self.set_bookmarked(event_id, bookmarked=True)

    def set_bookmarked(self, event_id: str, *, bookmarked: bool) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE events SET interested = ? WHERE event_id = ?",
                (int(bookmarked), event_id),
            )
        return cursor.rowcount == 1

    def mute_event(self, event_id: str) -> None:
        with self._connect() as connection:
            connection.execute("UPDATE events SET muted = 1 WHERE event_id = ?", (event_id,))

    def get_event_state(self, event_id: str) -> dict[str, bool]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT interested, muted FROM events WHERE event_id = ?", (event_id,)
            ).fetchone()
        if row is None:
            raise KeyError(event_id)
        return {"interested": bool(row[0]), "muted": bool(row[1])}

    def record_source_error(
        self, source: str, error: str, *, now: datetime | None = None
    ) -> dict[str, Any]:
        timestamp = _timestamp(now)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO source_health "
                "(source, last_error_at, error_streak, last_error) VALUES (?, ?, 1, ?) "
                "ON CONFLICT(source) DO UPDATE SET last_error_at = excluded.last_error_at, "
                "error_streak = source_health.error_streak + 1, last_error = excluded.last_error",
                (source, timestamp, error[:500]),
            )
        return self.get_source_health(source)

    def record_source_success(
        self, source: str, event_count: int, *, now: datetime | None = None
    ) -> dict[str, Any]:
        timestamp = _timestamp(now)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO source_health "
                "(source, last_success_at, error_streak, event_count) VALUES (?, ?, 0, ?) "
                "ON CONFLICT(source) DO UPDATE SET last_success_at = excluded.last_success_at, "
                "error_streak = 0, last_error = '', event_count = excluded.event_count",
                (source, timestamp, event_count),
            )
        return self.get_source_health(source)

    def get_source_health(self, source: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT source, last_success_at, last_error_at, error_streak, last_error, "
                "event_count, last_warned_at FROM source_health WHERE source = ?",
                (source,),
            ).fetchone()
        if row is None:
            raise KeyError(source)
        return _health_row(row)

    def list_source_health(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT source, last_success_at, last_error_at, error_streak, last_error, "
                "event_count, last_warned_at FROM source_health ORDER BY source"
            ).fetchall()
        return [_health_row(row) for row in rows]

    def should_warn_source(self, source: str, *, threshold: int, now: datetime) -> bool:
        health = self.get_source_health(source)
        if int(health["error_streak"]) < threshold:
            return False
        warned_at = _parse_datetime(str(health["last_warned_at"]))
        return warned_at is None or now.astimezone(UTC) - warned_at >= timedelta(days=1)

    def mark_source_warned(self, source: str, *, now: datetime) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE source_health SET last_warned_at = ? WHERE source = ?",
                (_timestamp(now), source),
            )

    def _find_matching_event(
        self, connection: sqlite3.Connection, event: CanonicalEvent
    ) -> str | None:
        row = connection.execute(
            "SELECT event_id FROM events WHERE event_id = ? OR canonical_url = ? LIMIT 1",
            (event["event_id"], event["canonical_url"]),
        ).fetchone()
        if row:
            return str(row[0])
        candidates = connection.execute(
            "SELECT event_id FROM events ORDER BY last_seen_at DESC LIMIT 500"
        ).fetchall()
        for candidate in candidates:
            existing = self._get_event(connection, str(candidate[0]))
            if events_match(existing, event):
                return str(candidate[0])
        return None

    def _insert_event(self, connection: sqlite3.Connection, event: CanonicalEvent) -> None:
        values = _event_values(event)
        connection.execute(
            "INSERT INTO events (event_id, title, normalized_title, canonical_url, status, "
            "listed_at, starts_at, ends_at, reg_deadline, submit_deadline, prize_pool_text, "
            "prize_pool_usd, mode, regions_json, stacks_json, crowd_score, confidence_json, "
            "description, team_size, eligibility, first_seen_at, last_seen_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            values,
        )

    def _update_event(
        self, connection: sqlite3.Connection, event_id: str, event: CanonicalEvent
    ) -> None:
        values = _event_values(event)
        connection.execute(
            "UPDATE events SET title=?, normalized_title=?, canonical_url=?, status=?, "
            "listed_at=?, "
            "starts_at=?, ends_at=?, reg_deadline=?, submit_deadline=?, prize_pool_text=?, "
            "prize_pool_usd=?, mode=?, regions_json=?, stacks_json=?, crowd_score=?, "
            "confidence_json=?, description=?, team_size=?, eligibility=?, first_seen_at=?, "
            "last_seen_at=? WHERE event_id=?",
            values[1:] + (event_id,),
        )

    def _insert_sighting(
        self, connection: sqlite3.Connection, event_id: str, sighting: Sighting
    ) -> None:
        connection.execute(
            "INSERT OR IGNORE INTO sightings (event_id, platform, url, seen_at, raw_ref) "
            "VALUES (?, ?, ?, ?, ?)",
            (event_id, sighting.platform, sighting.url, sighting.seen_at, sighting.raw_ref),
        )

    def _get_event(self, connection: sqlite3.Connection, event_id: str) -> CanonicalEvent:
        row = connection.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()
        if row is None:
            raise KeyError(event_id)
        sources = connection.execute(
            "SELECT platform, url, seen_at FROM sightings WHERE event_id = ? "
            "ORDER BY seen_at, platform",
            (event_id,),
        ).fetchall()
        return _event_row(row, sources)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0, check_same_thread=False)
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection


def _event_values(event: CanonicalEvent) -> tuple[Any, ...]:
    return (
        event["event_id"],
        event["title"],
        event["normalized_title"],
        event["canonical_url"],
        event["status"],
        event["listed_at"],
        event["starts_at"],
        event["ends_at"],
        event["reg_deadline"],
        event["submit_deadline"],
        event["prize_pool_text"],
        event["prize_pool_usd"],
        event["mode"],
        json.dumps(event["regions"]),
        json.dumps(event["stacks"]),
        event["crowd_score"],
        json.dumps(event["confidence"]),
        event["description"],
        event.get("team_size", ""),
        event.get("eligibility", ""),
        event["listed_at"],
        datetime.now(UTC).isoformat(),
    )


def _event_row(row: tuple[Any, ...], sources: list[tuple[Any, ...]]) -> CanonicalEvent:
    return {
        "event_id": str(row[0]),
        "title": str(row[1]),
        "normalized_title": str(row[2]),
        "canonical_url": str(row[3]),
        "status": str(row[4]),
        "listed_at": str(row[5]),
        "starts_at": str(row[6]),
        "ends_at": str(row[7]),
        "reg_deadline": str(row[8]),
        "submit_deadline": str(row[9]),
        "prize_pool_text": str(row[10]),
        "prize_pool_usd": int(row[11]) if row[11] is not None else None,
        "mode": str(row[12]),
        "regions": list(json.loads(str(row[13]))),
        "stacks": list(json.loads(str(row[14]))),
        "crowd_score": int(row[15]) if row[15] is not None else None,
        "confidence": dict(json.loads(str(row[16]))),
        "description": str(row[17]),
        "team_size": str(row[18]),
        "eligibility": str(row[19]),
        "sources": [
            {"platform": str(item[0]), "url": str(item[1]), "seen_at": str(item[2])}
            for item in sources
        ],
    }


def _merge_event(existing: CanonicalEvent, incoming: CanonicalEvent) -> CanonicalEvent:
    merged = dict(existing)
    for key, value in incoming.items():
        if key in {"event_id", "sources", "listed_at"}:
            continue
        if value not in ("", None, [], {}):
            merged[key] = value
    merged["event_id"] = existing["event_id"]
    merged["listed_at"] = min(existing["listed_at"], incoming["listed_at"])
    merged["sources"] = existing["sources"]
    return merged  # type: ignore[return-value]


def _material_changes(
    existing: CanonicalEvent, incoming: CanonicalEvent
) -> dict[str, tuple[str, str]]:
    changes = {}
    for field_name in MATERIAL_FIELDS:
        old = str(existing.get(field_name) or "")
        new = str(incoming.get(field_name) or "")
        if new and old != new:
            changes[field_name] = (old, new)
    return changes


def _health_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "source": str(row[0]),
        "last_success_at": str(row[1] or ""),
        "last_error_at": str(row[2] or ""),
        "error_streak": int(row[3]),
        "last_error": str(row[4] or ""),
        "event_count": int(row[5]),
        "last_warned_at": str(row[6] or ""),
    }


def _timestamp(value: datetime | None) -> str:
    current = value or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone(UTC).isoformat()


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _event_deadline(event: CanonicalEvent) -> datetime | None:
    values = [value for value in (event["reg_deadline"], event["submit_deadline"]) if value]
    if not values:
        return None
    try:
        return datetime.fromisoformat(min(values)).replace(tzinfo=UTC)
    except ValueError:
        return None


def _is_due_within(event: CanonicalEvent, current: datetime, cutoff: datetime) -> bool:
    deadline = _event_deadline(event)
    return deadline is not None and current < deadline <= cutoff


def _deadline_sort_key(event: CanonicalEvent) -> str:
    values = [value for value in (event["reg_deadline"], event["submit_deadline"]) if value]
    return min(values) if values else "9999-12-31"


def _is_event_id_prefix(value: str) -> bool:
    return 8 <= len(value) <= 40 and all(character in "0123456789abcdef" for character in value)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    normalized_title TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    status TEXT NOT NULL,
    listed_at TEXT NOT NULL,
    starts_at TEXT NOT NULL DEFAULT '',
    ends_at TEXT NOT NULL DEFAULT '',
    reg_deadline TEXT NOT NULL DEFAULT '',
    submit_deadline TEXT NOT NULL DEFAULT '',
    prize_pool_text TEXT NOT NULL DEFAULT '',
    prize_pool_usd INTEGER,
    mode TEXT NOT NULL DEFAULT 'unknown',
    regions_json TEXT NOT NULL DEFAULT '[]',
    stacks_json TEXT NOT NULL DEFAULT '[]',
    crowd_score INTEGER,
    confidence_json TEXT NOT NULL DEFAULT '{}',
    description TEXT NOT NULL DEFAULT '',
    team_size TEXT NOT NULL DEFAULT '',
    eligibility TEXT NOT NULL DEFAULT '',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    interested INTEGER NOT NULL DEFAULT 0,
    muted INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_events_url ON events(canonical_url);
CREATE INDEX IF NOT EXISTS idx_events_status_deadline ON events(status, submit_deadline);
CREATE TABLE IF NOT EXISTS sightings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL REFERENCES events(event_id),
    platform TEXT NOT NULL,
    url TEXT NOT NULL,
    seen_at TEXT NOT NULL,
    raw_ref TEXT NOT NULL DEFAULT '',
    UNIQUE(event_id, platform, url)
);
CREATE TABLE IF NOT EXISTS alerts_sent (
    alert_key TEXT PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES events(event_id),
    alert_type TEXT NOT NULL,
    sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS source_health (
    source TEXT PRIMARY KEY,
    last_success_at TEXT NOT NULL DEFAULT '',
    last_error_at TEXT NOT NULL DEFAULT '',
    error_streak INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    event_count INTEGER NOT NULL DEFAULT 0,
    last_warned_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS user_prefs (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    prefs_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS queued_alerts (
    alert_key TEXT PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES events(event_id),
    alert_type TEXT NOT NULL,
    deliver_at TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}'
);
"""
