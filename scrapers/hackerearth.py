from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

import httpx

from models import Hackathon, normalize_hackathon
from scrapers.common import iso_date, make_client

API_URL = "https://www.hackerearth.com/api/community/challenges/compete/"
PLATFORM = "HackerEarth"


def fetch() -> list[dict]:
    with make_client() as client:
        return _fetch(client)


def _fetch(client: httpx.Client) -> list[Hackathon]:
    response = client.get(
        API_URL,
        headers={"Referer": "https://www.hackerearth.com/challenges/hackathon/"},
    )
    response.raise_for_status()
    today = datetime.now(UTC).date().isoformat()
    return [
        parse_item(item)
        for item in response.json().get("data", [])
        if str(item.get("type", "")).lower() == "hackathon" and iso_date(item.get("end")) >= today
    ]


def parse_item(item: dict[str, Any]) -> Hackathon:
    team_size = _team_size(item.get("min_team_size"), item.get("max_team_size"))
    raw = {
        "title": item.get("title"),
        "url": urljoin("https://www.hackerearth.com", str(item.get("url") or "")),
        "platform": PLATFORM,
        "start_date": iso_date(item.get("start")),
        "end_date": iso_date(item.get("end")),
        "deadline": iso_date(item.get("end")),
        "team_size": team_size,
        "description": f"Hosted by {item.get('company_name')}" if item.get("company_name") else "",
    }
    return normalize_hackathon(raw)


def _team_size(minimum: object, maximum: object) -> str:
    if minimum and maximum:
        return str(minimum) if minimum == maximum else f"{minimum}–{maximum}"
    return str(maximum or minimum or "")
