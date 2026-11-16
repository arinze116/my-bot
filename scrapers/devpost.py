from __future__ import annotations

import os
import re
import time

import httpx

from models import Hackathon, normalize_hackathon
from scrapers.common import clean_html, make_client, parse_devpost_dates

API_URL = "https://devpost.com/api/hackathons"
PLATFORM = "Devpost"


def fetch() -> list[dict]:
    max_pages = max(1, int(os.getenv("DEVPOST_MAX_PAGES", "2")))
    with make_client() as client:
        return _fetch_pages(client, max_pages=max_pages)


def _fetch_pages(client: httpx.Client, *, max_pages: int) -> list[Hackathon]:
    hackathons: list[Hackathon] = []
    for page in range(1, max_pages + 1):
        response = client.get(
            API_URL,
            params={"status[]": "open", "order_by": "recently-added", "page": page},
        )
        response.raise_for_status()
        items = response.json().get("hackathons", [])
        hackathons.extend(parse_item(item) for item in items)
        if len(items) < 9:
            break
        if page < max_pages:
            time.sleep(3)
    return hackathons


def parse_item(item: dict[str, object]) -> Hackathon:
    start_date, deadline = parse_devpost_dates(str(item.get("submission_period_dates", "")))
    location = item.get("displayed_location") or {}
    themes = item.get("themes") or []
    raw = {
        "title": item.get("title"),
        "url": item.get("url"),
        "platform": PLATFORM,
        "prize": re.sub(r"^\$\s+", "$", clean_html(str(item.get("prize_amount") or ""))),
        "start_date": start_date,
        "end_date": deadline,
        "deadline": deadline,
        "mode": location.get("location") if isinstance(location, dict) else "",
        "tech_tags": [theme.get("name") for theme in themes if isinstance(theme, dict)],
        "eligibility": "Invite only" if item.get("invite_only") else "Open listing",
    }
    return normalize_hackathon(raw)
