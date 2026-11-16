from __future__ import annotations

import os
import re
from datetime import UTC, datetime

import httpx
from bs4 import BeautifulSoup

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "Chrome/142.0.0.0 Safari/537.36 HackathonRadar/1.0"
)


def make_client(timeout_seconds: float | None = None) -> httpx.Client:
    timeout_seconds = timeout_seconds or float(os.getenv("HTTP_TIMEOUT_SECONDS", "15"))
    if timeout_seconds <= 0 or timeout_seconds > 20:
        raise ValueError("HTTP_TIMEOUT_SECONDS must be greater than 0 and no more than 20")
    timeout = httpx.Timeout(
        timeout_seconds,
        connect=timeout_seconds,
        read=timeout_seconds,
        write=timeout_seconds,
        pool=timeout_seconds,
    )
    return httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "application/json,text/html,application/xhtml+xml,*/*;q=0.8",
        },
    )


def clean_html(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(BeautifulSoup(value, "lxml").get_text(" ", strip=True).split())


def iso_date(value: str | None) -> str:
    if not value:
        return ""
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", value)
    return match.group(1) if match else ""


def unix_date(value: object) -> str:
    try:
        return datetime.fromtimestamp(int(value), tz=UTC).date().isoformat()
    except (TypeError, ValueError, OSError):
        return ""


def parse_devpost_dates(value: str) -> tuple[str, str]:
    value = " ".join(value.replace("–", "-").split())
    for pattern in _DEVPOST_PATTERNS:
        match = pattern.fullmatch(value)
        if match:
            return _dates_from_match(match)
    return "", ""


_DEVPOST_PATTERNS = (
    re.compile(
        r"(?P<sm>[A-Za-z]{3}) (?P<sd>\d{1,2}), (?P<sy>\d{4}) - "
        r"(?P<em>[A-Za-z]{3}) (?P<ed>\d{1,2}), (?P<ey>\d{4})"
    ),
    re.compile(
        r"(?P<sm>[A-Za-z]{3}) (?P<sd>\d{1,2}) - "
        r"(?P<em>[A-Za-z]{3}) (?P<ed>\d{1,2}), (?P<ey>\d{4})"
    ),
    re.compile(r"(?P<sm>[A-Za-z]{3}) (?P<sd>\d{1,2}) - (?P<ed>\d{1,2}), (?P<ey>\d{4})"),
)


def _dates_from_match(match: re.Match[str]) -> tuple[str, str]:
    values = match.groupdict()
    end_year = int(values["ey"])
    end_month = datetime.strptime(values.get("em") or values["sm"], "%b").month
    start_month = datetime.strptime(values["sm"], "%b").month
    start_year = int(values.get("sy") or (end_year - 1 if start_month > end_month else end_year))
    start = datetime(start_year, start_month, int(values["sd"])).date().isoformat()
    end = datetime(end_year, end_month, int(values["ed"])).date().isoformat()
    return start, end
