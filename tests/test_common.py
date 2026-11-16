from __future__ import annotations

from scrapers.common import make_client, parse_devpost_dates


def test_http_client_uses_bounded_timeouts() -> None:
    client = make_client(15)
    try:
        timeout = client.timeout
        assert timeout.connect <= 20
        assert timeout.read <= 20
        assert timeout.write <= 20
        assert timeout.pool <= 20
    finally:
        client.close()


def test_parse_devpost_same_year_range() -> None:
    assert parse_devpost_dates("Oct 30 - Dec 04, 2026") == ("2026-10-30", "2026-12-04")


def test_parse_devpost_cross_year_range() -> None:
    assert parse_devpost_dates("Nov 15, 2026 - Jan 25, 2027") == (
        "2026-11-15",
        "2027-01-25",
    )
