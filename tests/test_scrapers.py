from __future__ import annotations

import json

from scrapers import devfolio, devpost, dorahacks, gitcoin, hackerearth, lablab, mlh, twitter


def test_devpost_item_normalization() -> None:
    item = devpost.parse_item(
        {
            "title": "Context Hack",
            "url": "https://context.devpost.com/",
            "submission_period_dates": "Nov 15, 2026 - Jan 25, 2027",
            "displayed_location": {"location": "Online"},
            "themes": [{"name": "Machine Learning/AI"}],
            "prize_amount": "$<span data-currency-value>100,000</span>",
            "invite_only": False,
        }
    )

    assert item["deadline"] == "2027-01-25"
    assert item["prize"] == "$100,000"
    assert item["tech_tags"] == "Machine Learning/AI"


def test_devfolio_embedded_json_parser() -> None:
    payload = {
        "props": {
            "pageProps": {
                "dehydratedState": {
                    "queries": [
                        {
                            "state": {
                                "data": {
                                    "open_hackathons": [
                                        {
                                            "slug": "future-hack",
                                            "name": "Future Hack",
                                            "starts_at": "2026-12-01T10:00:00Z",
                                            "ends_at": "2026-12-03T10:00:00Z",
                                            "is_online": True,
                                            "themes": [{"theme": {"name": "AI"}}],
                                            "settings": {"reg_ends_at": "2026-11-30T10:00:00Z"},
                                        }
                                    ]
                                }
                            }
                        }
                    ]
                }
            }
        }
    }
    html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script>'

    assert devfolio.parse_html(html)[0]["url"] == "https://future-hack.devfolio.co/"


def test_dorahacks_item_normalization() -> None:
    item = dorahacks.parse_item(
        {
            "id": 2442,
            "uname": "qday",
            "title": "Aevum Builder Challenge",
            "timeline_start": 1793772000,
            "timeline_end": 1796976000,
            "venue_form": "Virtual",
            "bonus_price": 1500,
            "bonus_token": "USD",
            "ecosystem": "Solidity,Foundry",
            "tags": "AI,Payments",
        }
    )

    assert item["url"] == "https://dorahacks.io/hackathon/qday"
    assert item["prize"] == "1,500 USD"
    assert item["mode"] == "Online"


def test_mlh_embedded_json_parser() -> None:
    payload = {
        "props": {
            "upcomingEvents": [
                {
                    "name": "Hack Western",
                    "websiteUrl": "https://hackwestern.com",
                    "startsAt": "2026-11-20T23:00:00Z",
                    "endsAt": "2026-11-22T20:00:00Z",
                    "formatType": "physical",
                    "location": "London, Ontario",
                    "customFields": {"hackathon_focus": ["Software", "Hardware"]},
                }
            ]
        }
    }
    html = f'<script data-page="app" type="application/json">{json.dumps(payload)}</script>'

    item = mlh.parse_html(html)[0]
    assert item["mode"] == "In-person (London, Ontario)"
    assert item["tech_tags"] == "Software, Hardware"


def test_lablab_card_parser() -> None:
    html = """
    <a href="/events/agent-hack"><h2>Agent Hack</h2>
      <time datetime="2026-12-10T00:00:00Z"></time><span data-tag>AI</span>
    </a>
    """

    item = lablab.parse_html(html)[0]
    assert item["title"] == "Agent Hack"
    assert item["deadline"] == "2026-12-10"


def test_hackerearth_item_normalization() -> None:
    item = hackerearth.parse_item(
        {
            "title": "ContextCon",
            "url": "/challenges/hackathon/contextcon/",
            "start": "2026-11-07T13:30:00",
            "end": "2027-01-17T17:30:00",
            "min_team_size": 1,
            "max_team_size": 4,
            "company_name": "YugabyteDB",
        }
    )

    assert item["team_size"] == "1–4"
    assert item["deadline"] == "2027-01-17"


def test_gitcoin_only_accepts_hackathon_or_bounty_campaigns() -> None:
    html = """
    <a href="/campaigns/grants-25"><h2>Gitcoin Grants 25</h2></a>
    <a href="/campaigns/builder-bounty"><h2>Builder Bounty</h2><p>Web3 builders</p></a>
    """

    items = gitcoin.parse_html(html)
    assert [item["title"] for item in items] == ["Builder Bounty"]


def test_twitter_item_uses_first_expanded_url() -> None:
    item = twitter.parse_item(
        {
            "id": "123",
            "text": "Applications open for our AI hackathon",
            "entities": {
                "urls": [{"expanded_url": "https://example.com/apply"}],
                "hashtags": [{"tag": "AI"}],
            },
        }
    )

    assert item["url"] == "https://example.com/apply"
    assert item["tech_tags"] == "AI"
