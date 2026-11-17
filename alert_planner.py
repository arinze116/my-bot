from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from event_model import CanonicalEvent
from event_store import UpsertResult

LAGOS = ZoneInfo("Africa/Lagos")


@dataclass(frozen=True, slots=True)
class UserPreferences:
    regions: tuple[str, ...] = ()
    stacks: tuple[str, ...] = ()
    modes: tuple[str, ...] = ()
    min_prize_usd: int | None = None
    muted_sources: tuple[str, ...] = ()
    muted_domains: tuple[str, ...] = ()
    muted_event_ids: tuple[str, ...] = ()
    paused: bool = False
    digest_enabled: bool = True
    quiet_hours_enabled: bool = True
    quiet_start: time = time(0, 30)
    quiet_end: time = time(6, 30)


@dataclass(frozen=True, slots=True)
class FilterDecision:
    matches: bool
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AlertPlan:
    alert_type: str
    alert_key: str
    deliver_at: datetime
    reasons: tuple[str, ...] = ()
    changes: dict[str, tuple[str, str]] = field(default_factory=dict)


def event_matches_filters(
    event: CanonicalEvent, preferences: UserPreferences
) -> FilterDecision:
    if event["event_id"] in preferences.muted_event_ids:
        return FilterDecision(False)
    muted_sources = {item.casefold() for item in preferences.muted_sources}
    if any(source["platform"].casefold() in muted_sources for source in event["sources"]):
        return FilterDecision(False)
    muted_domains = {item.casefold().removeprefix("www.") for item in preferences.muted_domains}
    event_domains = {
        urlsplit(event["canonical_url"]).netloc.casefold().removeprefix("www."),
        *(
            urlsplit(source["url"]).netloc.casefold().removeprefix("www.")
            for source in event["sources"]
        ),
    }
    if muted_domains & event_domains:
        return FilterDecision(False)
    if preferences.modes and event["mode"] not in {"unknown", *preferences.modes}:
        return FilterDecision(False)
    if preferences.min_prize_usd is not None:
        prize = event["prize_pool_usd"]
        if prize is not None and prize < preferences.min_prize_usd:
            return FilterDecision(False)
    reasons: list[str] = []
    if preferences.regions:
        matches = sorted(set(event["regions"]) & set(preferences.regions))
        if not matches:
            return FilterDecision(False)
        reasons.extend(_display_tag(item) for item in matches)
    if preferences.stacks:
        matches = sorted(set(event["stacks"]) & set(preferences.stacks))
        if not matches:
            return FilterDecision(False)
        reasons.extend(_display_tag(item) for item in matches)
    return FilterDecision(True, tuple(reasons))


class AlertPlanner:
    def __init__(self, preferences: UserPreferences) -> None:
        self.preferences = preferences

    def plan_upsert(
        self, event: CanonicalEvent, result: UpsertResult, *, now: datetime
    ) -> list[AlertPlan]:
        if self.preferences.paused:
            return []
        decision = event_matches_filters(event, self.preferences)
        if not decision.matches:
            return []
        if result.is_new:
            return [
                AlertPlan(
                    "new",
                    f"new:{event['event_id']}",
                    _deliver_at(now, self.preferences),
                    reasons=decision.reasons,
                )
            ]
        if result.material_changes:
            digest = hashlib.sha256(
                json.dumps(result.material_changes, sort_keys=True).encode()
            ).hexdigest()[:12]
            return [
                AlertPlan(
                    "change",
                    f"change:{event['event_id']}:{digest}",
                    _deliver_at(now, self.preferences),
                    reasons=decision.reasons,
                    changes=result.material_changes,
                )
            ]
        return []

    def plan_deadline(self, event: CanonicalEvent, *, now: datetime) -> AlertPlan | None:
        deadline = _deadline(event)
        if deadline is None or self.preferences.paused:
            return None
        decision = event_matches_filters(event, self.preferences)
        if not decision.matches:
            return None
        hours = (deadline - _as_utc(now)).total_seconds() / 3600
        if 0 < hours <= 24:
            prefix, alert_type = "deadline24", "deadline_soon"
        elif 24 < hours <= 72:
            prefix, alert_type = "deadline72", "deadline_soon"
        else:
            return None
        return AlertPlan(
            alert_type,
            f"{prefix}:{event['event_id']}",
            _deliver_at(now, self.preferences),
            reasons=decision.reasons,
        )

    def ongoing_digest_key(self, *, now: datetime) -> str | None:
        if self.preferences.paused or not self.preferences.digest_enabled:
            return None
        local = _as_utc(now).astimezone(LAGOS)
        if _in_quiet_hours(
            local.time(),
            self.preferences.quiet_start,
            self.preferences.quiet_end,
        ):
            return None
        return f"ongoing_digest:{local.date().isoformat()}"


def preferences_from_mapping(value: dict[str, object]) -> UserPreferences:
    return UserPreferences(
        regions=_string_tuple(value.get("regions")),
        stacks=_string_tuple(value.get("stacks")),
        modes=_string_tuple(value.get("modes")),
        min_prize_usd=_optional_int(value.get("min_prize_usd")),
        muted_sources=_string_tuple(value.get("muted_sources")),
        muted_domains=_string_tuple(value.get("muted_domains")),
        muted_event_ids=_string_tuple(value.get("muted_event_ids")),
        paused=bool(value.get("paused", False)),
        digest_enabled=bool(value.get("digest_enabled", True)),
        quiet_hours_enabled=bool(value.get("quiet_hours_enabled", True)),
        quiet_start=_parse_time(value.get("quiet_start"), time(0, 30)),
        quiet_end=_parse_time(value.get("quiet_end"), time(6, 30)),
    )


def preferences_to_mapping(preferences: UserPreferences) -> dict[str, object]:
    return {
        "regions": list(preferences.regions),
        "stacks": list(preferences.stacks),
        "modes": list(preferences.modes),
        "min_prize_usd": preferences.min_prize_usd,
        "muted_sources": list(preferences.muted_sources),
        "muted_domains": list(preferences.muted_domains),
        "muted_event_ids": list(preferences.muted_event_ids),
        "paused": preferences.paused,
        "digest_enabled": preferences.digest_enabled,
        "quiet_hours_enabled": preferences.quiet_hours_enabled,
        "quiet_start": preferences.quiet_start.strftime("%H:%M"),
        "quiet_end": preferences.quiet_end.strftime("%H:%M"),
    }


def _deliver_at(now: datetime, preferences: UserPreferences) -> datetime:
    current = _as_utc(now)
    if not preferences.quiet_hours_enabled:
        return current
    local = current.astimezone(LAGOS)
    if not _in_quiet_hours(local.time(), preferences.quiet_start, preferences.quiet_end):
        return current
    due_date = local.date()
    if preferences.quiet_start > preferences.quiet_end and local.time() >= preferences.quiet_start:
        due_date += timedelta(days=1)
    due = datetime.combine(due_date, preferences.quiet_end, tzinfo=LAGOS)
    return due.astimezone(UTC)


def _in_quiet_hours(current: time, start: time, end: time) -> bool:
    if start < end:
        return start <= current < end
    return current >= start or current < end


def _deadline(event: CanonicalEvent) -> datetime | None:
    values = [value for value in (event["reg_deadline"], event["submit_deadline"]) if value]
    if not values:
        return None
    try:
        parsed = date.fromisoformat(min(values))
    except ValueError:
        return None
    return datetime.combine(parsed, time.min, tzinfo=UTC)


def _display_tag(value: str) -> str:
    return value.replace("_", " ").title()


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(item).strip().casefold() for item in value if str(item).strip())


def _optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def _parse_time(value: object, default: time) -> time:
    try:
        return time.fromisoformat(str(value))
    except ValueError:
        return default


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
