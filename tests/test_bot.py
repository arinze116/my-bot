from __future__ import annotations

import logging

import httpx

from bot import TELEGRAM_MESSAGE_LIMIT, TelegramClient, format_message

HACKATHON = {
    "title": "AI_[Builders] Hack",
    "url": "https://example.com/apply?round=(1)",
    "platform": "Example",
    "prize": "$10,000",
    "start_date": "2026-12-01",
    "end_date": "2026-12-03",
    "deadline": "2026-11-30",
    "mode": "Online",
    "tech_tags": "AI, Machine Learning",
    "team_size": "1–4",
    "eligibility": "Open to all",
    "description": "Build *useful* systems. " * 300,
}


def test_format_message_escapes_markdown_and_fits_limit() -> None:
    message = format_message(HACKATHON)

    assert "AI\\_\\[Builders\\] Hack" in message
    assert "https://example.com/apply?round=(1\\)" in message
    assert len(message) <= TELEGRAM_MESSAGE_LIMIT


def test_format_message_preserves_link_under_adversarial_field_lengths() -> None:
    huge = {
        "title": "_" * 300,
        "url": f"https://example.com/{'a' * 1200}",
        "platform": "_" * 80,
        "prize": "_" * 500,
        "start_date": "_" * 500,
        "end_date": "_" * 500,
        "deadline": "_" * 500,
        "mode": "_" * 500,
        "tech_tags": "_" * 500,
        "team_size": "_" * 500,
        "eligibility": "_" * 500,
        "description": "_" * 400,
    }

    message = format_message(huge)

    assert len(message) <= TELEGRAM_MESSAGE_LIMIT
    assert "[Apply / View Hackathon](https://example.com/" in message


def test_format_message_does_not_wrap_untrusted_description_in_markdown_entity() -> None:
    hackathon = {
        **HACKATHON,
        "description": (
            "@shipordie_ Day 1 of the $100K Hackathon. Research notes https://t.co/i41xJICRtL"
        ),
    }

    message = format_message(hackathon)

    assert "📝 _" not in message
    assert "📝 @shipordie\\_ Day 1" in message


def test_format_message_omits_empty_fields() -> None:
    hackathon = {
        "title": "Signal Hack",
        "url": "https://example.com/signal-hack",
        "platform": "X/Twitter",
        "prize": None,
        "start_date": "",
        "end_date": "Not listed",
        "deadline": None,
        "mode": "Online",
    }

    message = format_message(hackathon)

    assert "📌 *Name:* Signal Hack" in message
    assert "🏷️ *Platform:* X/Twitter" in message
    assert "🌍 *Mode:* Online" in message
    assert "Not listed" not in message
    assert "*Prize Pool:*" not in message
    assert "*Start Date:*" not in message
    assert "*End Date:*" not in message
    assert "*Deadline:*" not in message
    assert "[Apply / View Hackathon](https://example.com/signal-hack)" in message


def test_format_message_shows_available_fields() -> None:
    message = format_message(HACKATHON)

    for label in (
        "Name",
        "Platform",
        "Prize Pool",
        "Start Date",
        "End Date",
        "Deadline",
        "Mode",
        "Tech / Tags",
        "Team Size",
        "Eligibility",
    ):
        assert f"*{label}:*" in message


def test_send_retries_three_times_then_stops(settings_factory) -> None:
    calls = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={"ok": False}, request=request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = TelegramClient(settings_factory(), client=http_client, sleeper=sleeps.append)

    assert client.send_hackathon(HACKATHON) is False
    assert calls == 3
    assert sleeps == [5.0, 5.0]


def test_permanent_error_is_not_retried(settings_factory) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400, json={"ok": False}, request=request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = TelegramClient(settings_factory(), client=http_client, sleeper=lambda _: None)

    assert client.send_hackathon(HACKATHON) is False
    assert calls == 1


def test_invalid_success_payload_is_not_retried(settings_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json", request=request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = TelegramClient(settings_factory(), client=http_client, sleeper=lambda _: None)

    assert client.send_hackathon(HACKATHON) is False


def test_failure_logs_do_not_expose_token(settings_factory, caplog) -> None:
    token = "canary-secret-token"

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network unavailable", request=request)

    settings = settings_factory(telegram_bot_token=token, telegram_retry_attempts=1)
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = TelegramClient(settings, client=http_client, sleeper=lambda _: None)

    with caplog.at_level(logging.WARNING):
        assert client.send_hackathon(HACKATHON) is False
    assert token not in caplog.text


def test_success_logs_do_not_expose_token(settings_factory, caplog) -> None:
    token = "ambient-log-canary"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True}, request=request)

    settings = settings_factory(telegram_bot_token=token)
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = TelegramClient(settings, client=http_client, sleeper=lambda _: None)

    with caplog.at_level(logging.INFO):
        assert client.send_hackathon(HACKATHON) is True
    assert token not in caplog.text
