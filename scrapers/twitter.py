from __future__ import annotations

import os
from typing import Any

import httpx

from config import DEFAULT_TWITTER_QUERIES
from models import Hackathon, normalize_hackathon
from scrapers.common import make_client

API_URL = "https://api.x.com/2/tweets/search/recent"
PLATFORM = "X/Twitter"
NOISE_PHRASES = (
    "won the hackathon",
    "we won",
    "our submission",
    "demo day recap",
)
NOISE_TERM_PAIRS = (
    ("hiring", "ex-hackathon"),
    ("course", "hackathon"),
    ("bootcamp", "hackathon"),
)


def fetch() -> list[dict]:
    token = os.getenv("TWITTER_BEARER_TOKEN", "").strip()
    if not token:
        return []
    queries = _queries(os.getenv("TWITTER_QUERIES", ""))
    with make_client() as client:
        return _fetch_queries(client, token=token, queries=queries)


def _fetch_queries(
    client: httpx.Client, *, token: str, queries: tuple[str, ...]
) -> list[Hackathon]:
    results: dict[str, Hackathon] = {}
    headers = {"Authorization": f"Bearer {token}"}
    for query in queries:
        response = client.get(
            API_URL,
            params={"query": query, "max_results": 100, "tweet.fields": "created_at,entities"},
            headers=headers,
        )
        response.raise_for_status()
        for item in response.json().get("data", []):
            if _is_noise(str(item.get("text") or "")):
                continue
            results[str(item.get("id"))] = parse_item(item)
    return list(results.values())


def parse_item(item: dict[str, Any]) -> Hackathon:
    text = " ".join(str(item.get("text") or "").split())
    entities = item.get("entities") or {}
    urls = entities.get("urls") or []
    first_url = urls[0].get("expanded_url") if urls else ""
    tweet_url = f"https://x.com/i/web/status/{item.get('id')}"
    hashtags = [tag.get("tag") for tag in entities.get("hashtags", [])]
    raw = {
        "title": text[:80],
        "url": first_url or tweet_url,
        "platform": PLATFORM,
        "tech_tags": hashtags,
        "description": text[:400],
    }
    return normalize_hackathon(raw)


def _queries(raw: str) -> tuple[str, ...]:
    parsed = tuple(value.strip() for value in raw.split("||") if value.strip())
    return parsed or DEFAULT_TWITTER_QUERIES


def _is_noise(text: str) -> bool:
    normalized = " ".join(text.lower().replace("’", "'").split())
    if any(phrase in normalized for phrase in NOISE_PHRASES):
        return True
    return any(all(term in normalized for term in pair) for pair in NOISE_TERM_PAIRS)
