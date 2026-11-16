from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from models import Hackathon, normalize_hackathon
from scrapers.common import make_client

LIST_URL = "https://gitcoin.co/campaigns"
PLATFORM = "Gitcoin"
MATCH = re.compile(r"\b(hackathon|buildathon|bounty)\b", re.IGNORECASE)


def fetch() -> list[dict]:
    with make_client() as client:
        response = client.get(LIST_URL)
        response.raise_for_status()
    return parse_html(response.text)


def parse_html(html: str) -> list[Hackathon]:
    soup = BeautifulSoup(html, "lxml")
    results: list[Hackathon] = []
    for anchor in soup.select('a[href^="/campaigns/"]'):
        text = " ".join(anchor.get_text(" ", strip=True).split())
        if not MATCH.search(text):
            continue
        heading = anchor.find(["h2", "h3", "h4"])
        title = heading.get_text(" ", strip=True) if heading else text[:200]
        raw = {
            "title": title,
            "url": urljoin(LIST_URL, str(anchor.get("href"))),
            "platform": PLATFORM,
            "tech_tags": "Web3",
            "description": text[:400],
        }
        results.append(normalize_hackathon(raw))
    return list({item["url"]: item for item in results}.values())
