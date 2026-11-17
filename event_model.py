from __future__ import annotations

import hashlib
import re
from datetime import UTC, date, datetime
from difflib import SequenceMatcher
from typing import NotRequired, TypedDict
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from models import Hackathon

TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {"ref", "source", "campaign", "fbclid", "gclid"}
MATERIAL_FIELDS = ("prize_pool_text", "reg_deadline", "submit_deadline", "status")


class EventSource(TypedDict):
    platform: str
    url: str
    seen_at: str


class CanonicalEvent(TypedDict):
    event_id: str
    title: str
    normalized_title: str
    canonical_url: str
    status: str
    listed_at: str
    starts_at: str
    ends_at: str
    reg_deadline: str
    submit_deadline: str
    prize_pool_text: str
    prize_pool_usd: int | None
    mode: str
    regions: list[str]
    stacks: list[str]
    crowd_score: int | None
    sources: list[EventSource]
    confidence: dict[str, str]
    description: str
    team_size: NotRequired[str]
    eligibility: NotRequired[str]


def canonicalize_hackathon(
    hackathon: Hackathon | dict[str, object], *, now: datetime | None = None
) -> CanonicalEvent:
    observed_at = _as_utc(now or datetime.now(UTC))
    title = _text(hackathon.get("title"))
    source_url = _text(hackathon.get("url"))
    platform = _text(hackathon.get("platform"))
    canonical_url = normalize_url(source_url)
    normalized_title = normalize_title(title)
    starts_at = _date_text(hackathon.get("start_date"))
    ends_at = _date_text(hackathon.get("end_date"))
    submit_deadline = _date_text(hackathon.get("deadline"))
    prize_text = _text(hackathon.get("prize"))
    searchable = " ".join(
        _text(hackathon.get(key))
        for key in ("title", "mode", "tech_tags", "eligibility", "description")
    )
    event_id = make_event_id(normalized_title, canonical_url, starts_at)
    return {
        "event_id": event_id,
        "title": title,
        "normalized_title": normalized_title,
        "canonical_url": canonical_url,
        "status": derive_status(starts_at, ends_at, submit_deadline, observed_at),
        "listed_at": observed_at.isoformat(),
        "starts_at": starts_at,
        "ends_at": ends_at,
        "reg_deadline": "",
        "submit_deadline": submit_deadline,
        "prize_pool_text": prize_text,
        "prize_pool_usd": parse_prize_usd(prize_text),
        "mode": normalize_mode(_text(hackathon.get("mode"))),
        "regions": infer_regions(searchable),
        "stacks": infer_stacks(searchable, _text(hackathon.get("tech_tags"))),
        "crowd_score": None,
        "sources": [
            {
                "platform": platform,
                "url": source_url,
                "seen_at": observed_at.isoformat(),
            }
        ],
        "confidence": {
            "title": "verified",
            "canonical_url": "verified",
            "dates": "verified" if starts_at or ends_at or submit_deadline else "unknown",
            "prize": "verified" if prize_text else "unknown",
            "regions": "inferred" if infer_regions(searchable) else "unknown",
            "stacks": "verified" if hackathon.get("tech_tags") else "inferred",
        },
        "description": _text(hackathon.get("description")),
        "team_size": _text(hackathon.get("team_size")),
        "eligibility": _text(hackathon.get("eligibility")),
    }


def make_event_id(normalized_title: str, canonical_url: str, starts_at: str) -> str:
    host = urlsplit(canonical_url).netloc.removeprefix("www.").casefold()
    raw = f"{normalized_title}|{host}|{starts_at}".encode()
    return hashlib.sha1(raw).hexdigest()  # noqa: S324 - non-security stable identity


def normalize_title(value: str) -> str:
    value = re.sub(r"\b20\d{2}\b", "", value.casefold())
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def normalize_url(value: str) -> str:
    parsed = urlsplit(value)
    filtered_query = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if key.casefold() not in TRACKING_QUERY_KEYS
        and not key.casefold().startswith(TRACKING_QUERY_PREFIXES)
    ]
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit(
        (parsed.scheme.casefold(), parsed.netloc.casefold(), path, urlencode(filtered_query), "")
    )


def events_match(first: CanonicalEvent, second: CanonicalEvent) -> bool:
    if first["canonical_url"] == second["canonical_url"]:
        return True
    if _shared_hosts(first, second) and _dates_overlap(first, second):
        score = SequenceMatcher(
            None,
            first["normalized_title"],
            second["normalized_title"],
        ).ratio()
        return score >= 0.86
    return False


def derive_status(starts_at: str, ends_at: str, deadline: str, now: datetime) -> str:
    today = now.date()
    start = _parse_date(starts_at)
    end = _parse_date(ends_at)
    due = _parse_date(deadline)
    if end and end < today:
        return "ended"
    if start and start <= today and (end is None or today <= end):
        return "ongoing"
    if due and due >= today:
        return "open_submission"
    if start and start > today:
        return "upcoming"
    return "unknown"


def normalize_mode(value: str) -> str:
    lowered = value.casefold()
    if "hybrid" in lowered or ("online" in lowered and "in-person" in lowered):
        return "hybrid"
    if "online" in lowered or "virtual" in lowered:
        return "online"
    if "person" in lowered or "onsite" in lowered or "on-site" in lowered:
        return "in_person"
    return "unknown"


def infer_regions(value: str) -> list[str]:
    lowered = value.casefold()
    aliases = {
        "africa": ("africa", "lagos", "nigeria", "kenya", "ghana"),
        "latam": ("latam", "latin america"),
        "india": ("india", "bangalore", "bengaluru", "delhi", "mumbai"),
        "sea": ("southeast asia", "sea hackathon", "singapore"),
        "eu": ("europe", " eu "),
        "global": ("worldwide", "global", "open to all"),
    }
    return sorted(key for key, terms in aliases.items() if any(term in lowered for term in terms))


def infer_stacks(searchable: str, tags: str) -> list[str]:
    lowered = f"{searchable} {tags}".casefold()
    aliases = {
        "ai": (" ai ", "artificial intelligence", "machine learning", "llm"),
        "solana": ("solana",),
        "web3": ("web3", "blockchain", "ethereum", "solidity"),
        "security": ("security", "cybersecurity"),
        "climate": ("climate",),
        "fintech": ("fintech", "payments"),
        "mobile": ("mobile", "android", "ios"),
        "open_source": ("open source", "opensource"),
    }
    padded = f" {lowered} "
    tokens = set(re.findall(r"[a-z0-9]+", lowered))
    return sorted(
        key
        for key, terms in aliases.items()
        if any(_has_term(term, padded, tokens) for term in terms)
    )


def _has_term(term: str, padded: str, tokens: set[str]) -> bool:
    normalized = " ".join(term.casefold().split())
    if " " not in normalized:
        return normalized in tokens
    return f" {normalized} " in padded


def parse_prize_usd(value: str) -> int | None:
    if not value or not any(marker in value.casefold() for marker in ("$", "usd")):
        return None
    match = re.search(r"\d[\d,]*(?:\.\d+)?", value)
    if not match:
        return None
    return int(float(match.group().replace(",", "")))


def _shared_hosts(first: CanonicalEvent, second: CanonicalEvent) -> bool:
    first_hosts = {
        _host(first["canonical_url"]),
        *(_host(item["url"]) for item in first["sources"]),
    }
    second_hosts = {
        _host(second["canonical_url"]),
        *(_host(item["url"]) for item in second["sources"]),
    }
    return bool((first_hosts & second_hosts) - {""})


def _dates_overlap(first: CanonicalEvent, second: CanonicalEvent) -> bool:
    first_start = _parse_date(first["starts_at"])
    second_start = _parse_date(second["starts_at"])
    if not first_start or not second_start:
        return False
    first_end = _parse_date(first["ends_at"]) or first_start
    second_end = _parse_date(second["ends_at"]) or second_start
    return first_start <= second_end and second_start <= first_end


def _host(value: str) -> str:
    return urlsplit(value).netloc.removeprefix("www.").casefold()


def _parse_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _date_text(value: object) -> str:
    text = _text(value)
    return text[:10] if _parse_date(text) else ""


def _text(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
