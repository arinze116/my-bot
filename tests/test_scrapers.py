from __future__ import annotations

import json

from config import DEFAULT_TWITTER_QUERIES
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


def test_default_twitter_queries_cover_requested_discovery_terms() -> None:
    joined = "\n".join(DEFAULT_TWITTER_QUERIES).lower()
    required_terms = {
        '"$"',
        '"24-hour hackathon"',
        '"48-hour hack"',
        '"africa hackathon"',
        '"ai hackathon"',
        '"applications open"',
        '"builders grant"',
        '"builders wanted"',
        '"call for builders"',
        '"campus hackathon"',
        '"climate hackathon"',
        '"join our hackathon"',
        '"lagos hackathon"',
        '"online hackathon"',
        '"open for registration"',
        '"open source hackathon"',
        '"prize pool hackathon"',
        '"register now"',
        '"student hackathon"',
        '"submit by"',
        '"university hackathon"',
        '"virtual hackathon"',
        '"we\'re hosting a hackathon"',
        '"week-long hackathon"',
        "aptos hackathon",
        "arbitrum hackathon",
        "base hackathon",
        "bounty hack",
        "buildathon",
        "celestia hackathon",
        "codeathon",
        "cosmos hackathon",
        "dorahacks",
        "encode club",
        "ethdenver",
        "ethglobal",
        "ethindia",
        "ethrome",
        "eventbrite",
        "filecoin hackathon",
        "fintech hackathon",
        "ghana hackathon",
        "gitcoin",
        "hackathon 2026",
        "hackathon kicks off",
        "hackathon starts",
        "hackathon weekend",
        "hackclub",
        "healthtech hackathon",
        "india hackathon",
        "kenya hackathon",
        "latam hackathon",
        "luma.com",
        "lu.ma",
        "mlh",
        "near hackathon",
        "nigeria hackathon",
        "optimism hackathon",
        "polygon hackathon",
        "protocol labs",
        "questbook",
        "robotics hackathon",
        "scroll hackathon",
        "sea hackathon",
        "solana hackathon",
        "starknet hackathon",
        "sui hackathon",
        "superteam",
        "taikai",
        "zksync hackathon",
    }

    assert required_terms <= {term for term in required_terms if term in joined}
    assert len(DEFAULT_TWITTER_QUERIES) == 8
    assert max(map(len, DEFAULT_TWITTER_QUERIES)) <= 512


def test_twitter_fetch_filters_requested_noise() -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "data": [
                    {"id": "1", "text": "Applications open for our Lagos hackathon"},
                    {"id": "2", "text": "We won the hackathon!"},
                    {"id": "3", "text": "Our submission and demo day recap"},
                    {"id": "4", "text": "New course about a hackathon"},
                    {"id": "5", "text": "Bootcamp hackathon lesson"},
                    {"id": "6", "text": "Hiring ex-hackathon participants"},
                ]
            }

    class FakeClient:
        def get(self, *args: object, **kwargs: object) -> FakeResponse:
            return FakeResponse()

    items = twitter._fetch_queries(FakeClient(), token="", queries=("hackathon",))

    assert [item["title"] for item in items] == ["Applications open for our Lagos hackathon"]
