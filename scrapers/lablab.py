from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from models import Hackathon, normalize_hackathon
from scrapers.common import iso_date, make_client

LIST_URL = "https://starfieldlabs.ai/events"
PLATFORM = "Lablab.ai / Starfield Labs"


def fetch() -> list[dict]:
    with make_client() as client:
        response = client.get(LIST_URL)
        response.raise_for_status()
    return parse_html(response.text)


def parse_html(html: str) -> list[Hackathon]:
    soup = BeautifulSoup(html, "lxml")
    results: list[Hackathon] = []
    for anchor in soup.select('a[href^="/event/"], a[href^="/events/"]'):
        if anchor.get("href") in {"/event", "/event/", "/events", "/events/"}:
            continue
        item = parse_card(anchor)
        if item:
            results.append(item)
    return list({item["url"]: item for item in results}.values())


def parse_card(anchor: Tag) -> Hackathon | None:
    heading = anchor.find(["h2", "h3", "h4"])
    title = heading.get_text(" ", strip=True) if heading else ""
    if not title:
        return None
    time_node = anchor.find("time")
    date_value = time_node.get("datetime", "") if isinstance(time_node, Tag) else ""
    raw = {
        "title": title,
        "url": urljoin(LIST_URL, str(anchor.get("href"))),
        "platform": PLATFORM,
        "deadline": iso_date(str(date_value)),
        "mode": "Online",
        "tech_tags": [tag.get_text(" ", strip=True) for tag in anchor.select("[data-tag]")],
    }
    return normalize_hackathon(raw)
