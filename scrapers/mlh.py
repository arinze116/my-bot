from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from models import Hackathon, normalize_hackathon
from scrapers.common import iso_date, make_client

PLATFORM = "MLH"
SEASON_URL = "https://www.mlh.com/seasons/{season}/events"


def fetch() -> list[dict]:
    seasons = _seasons()
    results: dict[str, Hackathon] = {}
    with make_client() as client:
        for index, season in enumerate(seasons):
            if index:
                time.sleep(3)
            response = client.get(SEASON_URL.format(season=season))
            response.raise_for_status()
            for item in parse_html(response.text):
                results[item["url"]] = item
    return list(results.values())


def parse_html(html: str) -> list[Hackathon]:
    soup = BeautifulSoup(html, "lxml")
    node = soup.find("script", attrs={"data-page": "app", "type": "application/json"})
    if node is None or not node.string:
        raise ValueError("MLH event payload not found")
    props = json.loads(node.string).get("props", {})
    return [parse_item(item) for item in props.get("upcomingEvents", [])]


def parse_item(item: dict[str, Any]) -> Hackathon:
    custom_fields = item.get("customFields") or {}
    raw = {
        "title": item.get("name"),
        "url": item.get("websiteUrl") or urljoin("https://www.mlh.com", item.get("url", "")),
        "platform": PLATFORM,
        "start_date": iso_date(item.get("startsAt")),
        "end_date": iso_date(item.get("endsAt")),
        "mode": _format_mode(item),
        "tech_tags": custom_fields.get("hackathon_focus", []),
        "eligibility": "Student-focused",
    }
    return normalize_hackathon(raw)


def _format_mode(item: dict[str, Any]) -> str:
    kind = str(item.get("formatType") or "").lower()
    label = {"physical": "In-person", "virtual": "Online", "hybrid": "Hybrid"}.get(
        kind, kind.title()
    )
    location = str(item.get("location") or "").strip()
    return f"{label}{f' ({location})' if location else ''}"


def _seasons() -> tuple[int, ...]:
    configured = os.getenv("MLH_SEASONS", "")
    if configured:
        return tuple(int(value.strip()) for value in configured.split(",") if value.strip())
    year = datetime.now(UTC).year
    return year, year + 1
