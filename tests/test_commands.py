from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx

from commands import BOT_COMMANDS, GRID_MARKUP, TelegramCommandPoller
from db import Database
from event_model import canonicalize_hackathon
from event_store import EventStore, Sighting


def test_grid_uses_two_columns_and_persistent_keyboard() -> None:
    rows = GRID_MARKUP["keyboard"]

    assert all(len(row) == 2 for row in rows)
    assert rows == [
        ["🆕 New", "🟢 Ongoing"],
        ["⏰ Soon", "🔖 Bookmarks"],
        ["🎯 Filters", "📡 Sources"],
        ["⏯ Alerts", "🌅 Digest"],
        ["📈 Vault", "⌨️ Hide"],
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


def test_status_reports_persisted_cycle_and_source_health(settings_factory) -> None:
    settings = settings_factory()
    database = Database(settings.database_path)
    database.init()
    store = EventStore(settings.database_path)
    store.init()
    started = datetime(2026, 11, 17, 11, 59, tzinfo=UTC)
    completed = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)
    store.begin_cycle(started)
    store.complete_cycle(
        fetched=18,
        sent=2,
        source_errors=1,
        delivery_failures=0,
        completed_at=completed,
    )
    store.record_source_success("devpost", 12, now=completed)
    store.record_source_error("twitter", "HTTP 503", now=completed)
    poller = TelegramCommandPoller(
        settings,
        database,
        ("Devpost", "X/Twitter"),
        event_store=store,
        clock=lambda: datetime(2026, 11, 17, 12, 5, tzinfo=UTC),
        client=httpx.Client(transport=httpx.MockTransport(lambda request: None)),
    )

    text, _, _ = poller._response_for("/status")

    assert text == (
        "<b>Radar status</b>\n"
        "Last scan · 5 min ago · 18 found\n"
        "Sources · 1/2 healthy · 1 failed"
    )


def test_status_reports_delivery_and_fatal_cycle_failures(settings_factory) -> None:
    settings = settings_factory()
    database = Database(settings.database_path)
    database.init()
    store = EventStore(settings.database_path)
    store.init()
    completed = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)
    store.begin_cycle(datetime(2026, 11, 17, 11, 59, tzinfo=UTC))
    store.complete_cycle(
        fetched=18,
        sent=0,
        source_errors=0,
        delivery_failures=1,
        completed_at=completed,
    )
    store.record_source_success("devpost", 18, now=completed)
    poller = TelegramCommandPoller(
        settings,
        database,
        ("Devpost",),
        event_store=store,
        clock=lambda: datetime(2026, 11, 17, 12, 5, tzinfo=UTC),
        client=httpx.Client(transport=httpx.MockTransport(lambda request: None)),
    )

    delivery_text, _, _ = poller._response_for("/status")
    assert delivery_text.endswith("Sources · 1/1 healthy · 1 delivery failed")

    store.begin_cycle(datetime(2026, 11, 17, 12, 6, tzinfo=UTC))
    store.fail_cycle("OperationalError", completed_at=datetime(2026, 11, 17, 12, 7, tzinfo=UTC))
    failure_text, _, _ = poller._response_for("/status")
    assert "Last scan failed · just now · OperationalError" in failure_text


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
        "/help": 7,
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


def test_start_does_not_reapply_rate_limited_bot_customization(
    settings_factory, monkeypatch
) -> None:
    settings = settings_factory()
    database = Database(settings.database_path)
    database.init()
    poller = TelegramCommandPoller(
        settings,
        database,
        ("Devpost",),
        client=httpx.Client(transport=httpx.MockTransport(lambda request: None)),
    )
    customization_calls = 0

    def customize() -> bool:
        nonlocal customization_calls
        customization_calls += 1
        return True

    monkeypatch.setattr(poller, "customize_bot", customize)
    monkeypatch.setattr(poller, "_prime_offset", lambda: None)
    monkeypatch.setattr(poller, "_poll_loop", lambda: None)

    poller.start()
    poller.stop()

    assert customization_calls == 0


def test_event_views_use_canonical_store_and_keep_one_event_per_line(settings_factory) -> None:
    settings = settings_factory()
    database = Database(settings.database_path)
    database.init()
    store = EventStore(settings.database_path)
    store.init()
    event = canonicalize_hackathon(
        {
            "title": "Africa AI Sprint",
            "url": "https://example.com/africa-ai",
            "platform": "DoraHacks",
            "start_date": "2026-11-16",
            "end_date": "2026-11-20",
            "deadline": "2026-11-18",
            "mode": "Online",
        },
        now=datetime(2026, 11, 17, 12, tzinfo=UTC),
    )
    store.upsert_event(
        event,
        Sighting("DoraHacks", event["canonical_url"], "2026-11-17T12:00:00+00:00"),
    )
    poller = TelegramCommandPoller(
        settings,
        database,
        ("DoraHacks",),
        event_store=store,
        clock=lambda: datetime(2026, 11, 17, 12, tzinfo=UTC),
        client=httpx.Client(transport=httpx.MockTransport(lambda request: None)),
    )

    new_text, _, _ = poller._response_for("/new")
    ongoing_text, _, _ = poller._response_for("/ongoing")
    soon_text, _, _ = poller._response_for("/soon")

    assert new_text.startswith("<b>New · 1</b>")
    assert ongoing_text.startswith("<b>Ongoing · 1</b>")
    assert soon_text.startswith("<b>Due soon · 1</b>")
    assert all(text.count("Africa AI Sprint") == 1 for text in (new_text, ongoing_text, soon_text))


def test_owner_controls_pause_resume_digest_and_filters(settings_factory) -> None:
    settings = settings_factory()
    database = Database(settings.database_path)
    database.init()
    store = EventStore(settings.database_path)
    store.init()
    poller = TelegramCommandPoller(
        settings,
        database,
        ("Devpost",),
        event_store=store,
        client=httpx.Client(transport=httpx.MockTransport(lambda request: None)),
    )

    pause_text, _, _ = poller._response_for("/pause")
    assert pause_text == "<b>Alerts paused</b>\nScanning continues. Push delivery is off."
    assert store.load_preferences()["paused"] is True

    digest_text, _, _ = poller._response_for("/digest off")
    assert digest_text == "<b>Digest off</b>\nNew and deadline alerts stay instant."
    assert store.load_preferences()["digest_enabled"] is False

    filter_text, _, _ = poller._response_for("/filters region africa,global")
    assert "Regions · Africa, Global" in filter_text
    assert store.load_preferences()["regions"] == ["africa", "global"]

    source_text, _, _ = poller._response_for("/mute Devpost")
    assert source_text == "<b>Source muted</b>\nDevpost will no longer alert."
    assert store.load_preferences()["muted_sources"] == ["devpost"]

    resume_text, _, _ = poller._response_for("/resume")
    assert resume_text == "<b>Alerts resumed</b>\nNew matches will arrive instantly."
    assert store.load_preferences()["paused"] is False


def test_bookmark_commands_add_list_and_remove(settings_factory) -> None:
    settings = settings_factory()
    database = Database(settings.database_path)
    database.init()
    store = EventStore(settings.database_path)
    store.init()
    event = canonicalize_hackathon(
        {"title": "Builders Hack", "url": "https://example.com/build", "platform": "Devpost"}
    )
    store.upsert_event(event, Sighting("Devpost", event["canonical_url"], event["listed_at"]))
    poller = TelegramCommandPoller(
        settings,
        database,
        ("Devpost",),
        event_store=store,
        client=httpx.Client(transport=httpx.MockTransport(lambda request: None)),
    )

    missing_text, _, _ = poller._response_for("/bookmark deadbeef")
    added_text, _, _ = poller._response_for(f"/bookmark {event['event_id'][:8]}")
    bookmarks_text, bookmarks_markup, _ = poller._response_for("🔖 Bookmarks")

    assert missing_text == "<b>Bookmark not changed</b>\nNo matching event was found."
    assert added_text == "<b>Bookmark added</b>\nBuilders Hack is saved."
    assert 'href="https://example.com/build"' in bookmarks_text
    assert bookmarks_markup == {
        "inline_keyboard": [
            [
                {
                    "text": "Remove · Builders Hack",
                    "callback_data": "unbookmark:" + event["event_id"],
                }
            ]
        ]
    }

    removed_text, _, _ = poller._response_for(f"/unbookmark {event['canonical_url']}")
    empty_text, empty_markup, _ = poller._response_for("/bookmarks")

    assert removed_text == "<b>Bookmark removed</b>\nBuilders Hack is no longer saved."
    assert empty_text == "<b>Bookmarks · 0</b>\nTap Bookmark on an alert to save it."
    assert empty_markup == GRID_MARKUP


def test_callback_actions_are_owner_locked_and_persist(settings_factory) -> None:
    payloads: list[tuple[str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append((request.url.path.rsplit("/", 1)[-1], json.loads(request.content)))
        return httpx.Response(200, json={"ok": True, "result": True}, request=request)

    settings = settings_factory()
    database = Database(settings.database_path)
    database.init()
    store = EventStore(settings.database_path)
    store.init()
    event = canonicalize_hackathon(
        {"title": "Builders Hack", "url": "https://example.com/build", "platform": "Devpost"}
    )
    store.upsert_event(event, Sighting("Devpost", event["canonical_url"], event["listed_at"]))
    poller = TelegramCommandPoller(
        settings,
        database,
        ("Devpost",),
        event_store=store,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert not poller.handle_update(
        {
            "callback_query": {
                "id": "unauthorized-callback",
                "data": "bookmark:" + event["event_id"],
                "message": {"chat": {"id": 999999}},
            }
        }
    )
    assert store.get_event_state(event["event_id"])["interested"] is False
    assert payloads == []

    assert poller.handle_update(
        {
            "callback_query": {
                "id": "callback-1",
                "data": "bookmark:" + event["event_id"],
                "message": {"chat": {"id": int(settings.telegram_chat_id)}},
            }
        }
    )
    assert store.get_event_state(event["event_id"])["interested"] is True
    assert payloads[-1] == (
        "answerCallbackQuery",
        {"callback_query_id": "callback-1", "text": "Bookmark added"},
    )

    assert poller.handle_update(
        {
            "callback_query": {
                "id": "callback-2",
                "data": "unbookmark:" + event["event_id"],
                "message": {
                    "message_id": 22,
                    "chat": {"id": int(settings.telegram_chat_id)},
                },
            }
        }
    )
    assert store.get_event_state(event["event_id"])["interested"] is False
    assert payloads[-2] == (
        "answerCallbackQuery",
        {"callback_query_id": "callback-2", "text": "Bookmark removed"},
    )
    assert payloads[-1][0] == "editMessageText"
    assert payloads[-1][1]["text"] == (
        "<b>Bookmarks · 0</b>\nTap Bookmark on an alert to save it."
    )

    assert poller.handle_update(
        {
            "callback_query": {
                "id": "callback-3",
                "data": "interest:" + event["event_id"],
                "message": {"chat": {"id": int(settings.telegram_chat_id)}},
            }
        }
    )
    assert store.get_event_state(event["event_id"])["interested"] is True
    assert payloads[-1] == (
        "answerCallbackQuery",
        {"callback_query_id": "callback-3", "text": "Bookmark added"},
    )
