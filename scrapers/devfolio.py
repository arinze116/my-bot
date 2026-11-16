from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from bs4 import BeautifulSoup

from models import Hackathon, normalize_hackathon
from scrapers.common import iso_date, make_client

LIST_URL = "https://devfolio.co/hackathons"
PLATFORM = "Devfolio"


def fetch() -> list[dict]:
    with make_client() as client:
        response = client.get(LIST_URL)
        response.raise_for_status()
    return parse_html(response.text)


def parse_html(html: str) -> list[Hackathon]:
    soup = BeautifulSoup(html, "lxml")
    node = soup.find("script", id="__NEXT_DATA__")
    if node is None or not node.string:
        raise ValueError("Devfolio __NEXT_DATA__ payload not found")
    data = json.loads(node.string)
    items = next(_find_named_lists(data, "open_hackathons"), [])
    return [parse_item(item) for item in items if isinstance(item, dict)]


def parse_item(item: dict[str, Any]) -> Hackathon:
    settings = item.get("settings") or {}
    slug = str(item.get("slug") or "").strip()
    url = settings.get("external_apply_url") or f"https://{slug}.devfolio.co/"
    themes = item.get("themes") or []
    raw = {
        "title": item.get("name"),
        "url": url,
        "platform": PLATFORM,
        "start_date": iso_date(item.get("starts_at")),
        "end_date": iso_date(item.get("ends_at")),
        "deadline": iso_date(settings.get("reg_ends_at")),
        "mode": "Online" if item.get("is_online") else "In-person",
        "tech_tags": [
            entry.get("theme", {}).get("name")
            for entry in themes
            if isinstance(entry, dict) and isinstance(entry.get("theme"), dict)
        ],
    }
    return normalize_hackathon(raw)


def _find_named_lists(value: object, key: str) -> Iterator[list[Any]]:
    if isinstance(value, dict):
        candidate = value.get(key)
        if isinstance(candidate, list):
            yield candidate
        for child in value.values():
            yield from _find_named_lists(child, key)
    elif isinstance(value, list):
        for child in value:
            yield from _find_named_lists(child, key)
