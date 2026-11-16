from __future__ import annotations

from typing import NotRequired, Required, TypedDict
from urllib.parse import urlsplit


class Hackathon(TypedDict, total=False):
    title: Required[str]
    url: Required[str]
    platform: Required[str]
    prize: NotRequired[str]
    start_date: NotRequired[str]
    end_date: NotRequired[str]
    deadline: NotRequired[str]
    mode: NotRequired[str]
    tech_tags: NotRequired[str]
    team_size: NotRequired[str]
    eligibility: NotRequired[str]
    description: NotRequired[str]


OPTIONAL_FIELDS = (
    "prize",
    "start_date",
    "end_date",
    "deadline",
    "mode",
    "tech_tags",
    "team_size",
    "eligibility",
    "description",
)


def normalize_hackathon(raw: dict[str, object]) -> Hackathon:
    title = _required_text(raw, "title")
    url = _required_url(raw)
    platform = _required_text(raw, "platform")
    result: Hackathon = {"title": title[:300], "url": url, "platform": platform[:80]}

    for field in OPTIONAL_FIELDS:
        value = _optional_text(raw.get(field))
        if value:
            result[field] = value[:400] if field == "description" else value[:500]
    return result


def _required_text(raw: dict[str, object], field: str) -> str:
    value = _optional_text(raw.get(field))
    if not value:
        raise ValueError(f"Missing required hackathon field: {field}")
    return value


def _required_url(raw: dict[str, object]) -> str:
    value = _required_text(raw, "url")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Hackathon URL must be absolute HTTP(S)")
    if len(value) > 1500:
        raise ValueError("Hackathon URL is too long for Telegram delivery")
    return value


def _optional_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        value = ", ".join(str(item) for item in value if item)
    return " ".join(str(value).split()).strip()
