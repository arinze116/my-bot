from __future__ import annotations

import re
from datetime import date, datetime

from bs4 import BeautifulSoup, Tag

from models import Hackathon, normalize_hackathon
from scrapers.common import make_client

EVENTS_URL = "https://ethglobal.com/events"
PLATFORM = "ETHGlobal"
MONTHS = {
    name: index
    for index, name in enumerate(
        (
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ),
        start=1,
    )
}


def fetch() -> list[dict]:
    with make_client() as client:
        response = client.get(EVENTS_URL)
        response.raise_for_status()
    today = date.today().isoformat()
    return [
        item
        for item in parse_html(response.text)
        if not item.get("end_date") or str(item["end_date"]) >= today
    ]


def parse_html(html: str) -> list[Hackathon]:
    soup = BeautifulSoup(html, "lxml")
    items: list[Hackathon] = []
    seen_urls: set[str] = set()
    for card in soup.select('a[href^="/events/"]'):
        title_node = card.find(["h2", "h3"])
        if not isinstance(title_node, Tag):
            continue
        title = " ".join(title_node.get_text(" ", strip=True).split())
        text = " ".join(card.get_text(" ", strip=True).split())
        if "hackathon" not in text.casefold() and "ethonline" not in title.casefold():
            continue
        href = str(card.get("href") or "")
        url = f"https://ethglobal.com{href}"
        if url in seen_urls:
            continue
        seen_urls.add(url)
        start_date, end_date = _dates(card, title)
        raw = {
            "title": title,
            "url": url,
            "platform": PLATFORM,
            "start_date": start_date,
            "end_date": end_date,
            "mode": "Online" if "online" in text.casefold() else "In-person",
            "tech_tags": "Web3, Ethereum",
            "description": text,
        }
        items.append(normalize_hackathon(raw))
    return items


def _dates(card: Tag, title: str) -> tuple[str, str]:
    time_values = list(
        dict.fromkeys(
            " ".join(node.get_text(" ", strip=True).split())
            for node in card.find_all("time")
            if node.get_text(" ", strip=True)
        )
    )
    title_year = _year(title)
    if time_values:
        end_text = time_values[1] if len(time_values) > 1 else time_values[0]
        end = _human_date(end_text, title_year)
        end_year = int(end[:4]) if end else title_year
        start = _human_date(time_values[0], end_year)
        return start, end

    month_name = next(
        (text for text in card.stripped_strings if text in MONTHS),
        "",
    )
    days = [
        int(text)
        for node in card.find_all("span")
        if (text := node.get_text(" ", strip=True)).isdigit()
    ]
    if not month_name or not days or not title_year:
        return "", ""
    month = MONTHS[month_name]
    start = datetime(title_year, month, days[0]).date().isoformat()
    end_day = days[1] if len(days) > 1 else days[0]
    end = datetime(title_year, month, end_day).date().isoformat()
    return start, end


def _human_date(value: str, default_year: int) -> str:
    cleaned = re.sub(r"(\d)(?:st|nd|rd|th)", r"\1", value.casefold())
    cleaned = cleaned.replace(",", "").title()
    for pattern in ("%b %d %Y", "%B %d %Y"):
        try:
            return datetime.strptime(cleaned, pattern).date().isoformat()
        except ValueError:
            pass
    for pattern in ("%b %d", "%B %d"):
        try:
            parsed = datetime.strptime(cleaned, pattern)
            return parsed.replace(year=default_year).date().isoformat()
        except ValueError:
            pass
    return ""


def _year(value: str) -> int:
    match = re.search(r"\b(20\d{2})\b", value)
    return int(match.group(1)) if match else datetime.now().year
