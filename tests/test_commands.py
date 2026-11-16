from __future__ import annotations

import json

import httpx

from commands import BOT_COMMANDS, GRID_MARKUP, TelegramCommandPoller
from db import Database


def test_grid_uses_two_columns_and_persistent_keyboard() -> None:
    rows = GRID_MARKUP["keyboard"]

    assert all(len(row) == 2 for row in rows)
    assert rows == [
        ["📡 Pulse", "✨ Fresh"],
        ["📈 Vault", "🌐 Coverage"],
        ["🧭 Guide", "⌨️ Hide"],
    ]
    assert GRID_MARKUP["resize_keyboard"] is True
    assert GRID_MARKUP["is_persistent"] is True


def test_unauthorized_chat_is_ignored(settings_factory) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True, "result": True}, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    database = Database(settings_factory().database_path)
    database.init()
    poller = TelegramCommandPoller(
        settings_factory(), database, ("Devpost", "X/Twitter"), client=client
    )

    handled = poller.handle_update({"message": {"chat": {"id": 999999}, "text": "/grid"}})

    assert handled is False
    assert requests == []


def test_grid_and_status_commands_send_owner_dashboard(settings_factory) -> None:
    payloads: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "result": True}, request=request)

    settings = settings_factory()
    database = Database(settings.database_path)
    database.init()
    database.mark_seen("1", "AI Builders Sprint", "Devpost")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    poller = TelegramCommandPoller(settings, database, ("Devpost", "X/Twitter"), client=client)

    assert poller.handle_update(
        {"message": {"chat": {"id": int(settings.telegram_chat_id)}, "text": "/grid"}}
    )
    assert poller.handle_update(
        {"message": {"chat": {"id": int(settings.telegram_chat_id)}, "text": "📡 Pulse"}}
    )

    assert payloads[0]["reply_markup"] == GRID_MARKUP
    assert payloads[0]["text"] == (
        "<b>Hackathon Radar</b>\n"
        "Arinze · 2 sources · 20-min scans\n\n"
        "Choose a view."
    )
    assert payloads[1]["text"] == (
        "<b>Radar online</b>\n"
        "Every 20 min · 2 sources · 1 saved\n"
        "Next scan within 20 min"
    )


def test_fresh_finds_are_clickable_and_escape_untrusted_copy(settings_factory) -> None:
    payloads: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "result": True}, request=request)

    settings = settings_factory()
    database = Database(settings.database_path)
    database.init()
    database.mark_seen(
        "1",
        "Build <ship> & win",
        "Devpost",
        "https://example.com/apply?round=1&track=ai",
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    poller = TelegramCommandPoller(settings, database, ("Devpost",), client=client)

    assert poller.handle_update(
        {"message": {"chat": {"id": int(settings.telegram_chat_id)}, "text": "✨ Fresh"}}
    )

    assert payloads[0]["parse_mode"] == "HTML"
    assert "Build &lt;ship&gt; &amp; win" in payloads[0]["text"]
    assert 'href="https://example.com/apply?round=1&amp;track=ai"' in payloads[0]["text"]
    assert "Open opportunity" not in payloads[0]["text"]


def test_command_outputs_stay_within_compact_line_budgets(settings_factory) -> None:
    settings = settings_factory()
    database = Database(settings.database_path)
    database.init()
    for index in range(7):
        database.mark_seen(
            str(index),
            f"Opportunity {index}",
            f"Source {index}",
            f"https://example.com/{index}",
        )
    poller = TelegramCommandPoller(
        settings,
        database,
        tuple(f"Source {index}" for index in range(8)),
        client=httpx.Client(transport=httpx.MockTransport(lambda request: None)),
    )

    budgets = {
        "/grid": 3,
        "/status": 3,
        "/latest": 5,
        "/stats": 7,
        "/sources": 3,
        "/help": 6,
    }
    for command, budget in budgets.items():
        text, _, _ = poller._response_for(command)
        meaningful_lines = [line for line in text.splitlines() if line.strip()]
        assert len(meaningful_lines) <= budget, (command, meaningful_lines)


def test_bot_customization_registers_minimal_commands(settings_factory) -> None:
    methods: list[str] = []
    command_payload: dict | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal command_payload
        methods.append(request.url.path.rsplit("/", 1)[-1])
        payload = json.loads(request.content)
        if methods[-1] == "setMyCommands":
            command_payload = payload
        return httpx.Response(200, json={"ok": True, "result": True}, request=request)

    settings = settings_factory()
    database = Database(settings.database_path)
    database.init()
    client = httpx.Client(transport=httpx.MockTransport(handler))
    poller = TelegramCommandPoller(settings, database, ("Devpost",), client=client)

    assert poller.customize_bot() is True
    assert methods == [
        "setMyName",
        "setMyDescription",
        "setMyShortDescription",
        "setMyCommands",
    ]
    assert command_payload == {"commands": list(BOT_COMMANDS)}
    assert BOT_COMMANDS == (
        {"command": "start", "description": "Open your private opportunity desk"},
        {"command": "grid", "description": "Show the Radar command grid"},
    )


def test_profile_photo_upload_uses_static_jpg_attachment(settings_factory, tmp_path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True, "result": True}, request=request)

    avatar = tmp_path / "radar.jpg"
    avatar.write_bytes(b"fake-jpg")
    settings = settings_factory()
    database = Database(settings.database_path)
    database.init()
    poller = TelegramCommandPoller(
        settings,
        database,
        ("Devpost",),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert poller.set_profile_photo(avatar) is True
    assert requests[0].url.path.endswith("/setMyProfilePhoto")
    assert "multipart/form-data" in requests[0].headers["content-type"]
    assert b'"type":"static"' in requests[0].content
    assert b"attach://avatar" in requests[0].content
