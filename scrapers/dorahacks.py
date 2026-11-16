from __future__ import annotations

import os
import time
from typing import Any

import httpx

from models import Hackathon, normalize_hackathon
from scrapers.common import DEFAULT_USER_AGENT, make_client, unix_date

API_URL = "https://dorahacks.io/api/v1/hub/hackathons"
PLATFORM = "DoraHacks"
STATUSES = ("upcoming", "ongoing")


def fetch() -> list[dict]:
    max_pages = max(1, int(os.getenv("DORAHACKS_MAX_PAGES", "2")))
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://dorahacks.io/hackathon",
    }
    with make_client() as client:
        return _fetch_all(client, headers=headers, max_pages=max_pages)


def _fetch_all(client: httpx.Client, *, headers: dict[str, str], max_pages: int) -> list[Hackathon]:
    by_id: dict[str, Hackathon] = {}
    request_number = 0
    for status in STATUSES:
        for page in range(1, max_pages + 1):
            if request_number:
                time.sleep(3)
            response = client.get(
                API_URL,
                params={"status": status, "page": page, "pageSize": 50},
                headers=headers,
            )
            request_number += 1
            response.raise_for_status()
            data = response.json()
            items = data.get("results") or []
            for item in items:
                key = str(item.get("id") or item.get("uname") or "")
                by_id[key] = parse_item(item)
            if not data.get("next"):
                break
    return list(by_id.values())


def parse_item(item: dict[str, Any]) -> Hackathon:
    slug = item.get("uname") or item.get("id")
    prize = _prize(item.get("bonus_price"), item.get("bonus_token"))
    raw = {
        "title": item.get("title"),
        "url": f"https://dorahacks.io/hackathon/{slug}",
        "platform": PLATFORM,
        "prize": prize,
        "start_date": unix_date(item.get("timeline_start")),
        "end_date": unix_date(item.get("timeline_end")),
        "deadline": unix_date(item.get("timeline_end")),
        "mode": _mode(item),
        "tech_tags": _tags(item),
    }
    return normalize_hackathon(raw)


def _prize(value: object, token: object) -> str:
    if value in {None, "", 0, "0"}:
        return ""
    currency = token or "USD"
    return f"{value:,} {currency}" if isinstance(value, (int, float)) else f"{value} {currency}"


def _mode(item: dict[str, Any]) -> str:
    form = str(item.get("venue_form") or "").strip()
    if form.lower() == "virtual":
        return "Online"
    place = ", ".join(
        str(item.get(field)) for field in ("venue_name", "venue_address") if item.get(field)
    )
    return f"{form or 'In-person'}{f' ({place})' if place else ''}"


def _tags(item: dict[str, Any]) -> str:
    values = [item.get("ecosystem"), item.get("tags")]
    return ", ".join(str(value) for value in values if value)
