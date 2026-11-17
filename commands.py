from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import UTC, date, datetime
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from alert_planner import (
    UserPreferences,
    preferences_from_mapping,
    preferences_to_mapping,
)
from config import Settings
from db import Database
from event_model import CanonicalEvent
from event_store import EventStore

LOGGER = logging.getLogger(__name__)
MAX_FRESH_ITEMS = 4
MAX_VAULT_SOURCES = 5
SOURCES_PER_LINE = 4

BOT_COMMANDS = (
    {"command": "start", "description": "Open your private opportunity desk"},
    {"command": "grid", "description": "Show the Radar command grid"},
)

GRID_MARKUP = {
    "keyboard": [
        ["🆕 New", "🟢 Ongoing"],
        ["⏰ Soon", "🎯 Filters"],
        ["📡 Sources", "⏯ Alerts"],
        ["🌅 Digest", "📈 Vault"],
        ["🧭 Guide", "⌨️ Hide"],
    ],
    "resize_keyboard": True,
    "is_persistent": True,
    "input_field_placeholder": "Open your opportunity desk",
}

REMOVE_GRID_MARKUP = {"remove_keyboard": True}


class TelegramCommandPoller:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        active_sources: Sequence[str],
        *,
        event_store: EventStore | None = None,
        clock: Callable[[], datetime] | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings
        self.database = database
        self.active_sources = tuple(active_sources)
        self.event_store = event_store
        self.clock = clock or (lambda: datetime.now(UTC))
        self._owns_client = client is None
        self.client = client or httpx.Client(timeout=_timeout(settings.http_timeout_seconds))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._offset: int | None = None

    def customize_bot(self) -> bool:
        calls = (
            ("setMyName", {"name": "Hackathon Radar"}),
            (
                "setMyDescription",
                {
                    "description": (
                        "Your private hackathon intelligence desk. I scan major platforms, cut "
                        "the noise, and deliver decision-ready opportunities with deadlines, "
                        "prizes, and direct links."
                    )
                },
            ),
            (
                "setMyShortDescription",
                {"short_description": "High-signal hackathon intelligence, delivered to you."},
            ),
            ("setMyCommands", {"commands": list(BOT_COMMANDS)}),
        )
        outcomes = [self._api_call(method, payload) is not None for method, payload in calls]
        return all(outcomes)

    def set_profile_photo(self, image_path: str | Path) -> bool:
        path = Path(image_path)
        if path.suffix.casefold() not in {".jpg", ".jpeg"}:
            raise ValueError("Telegram static profile photos must use JPG format")
        endpoint = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/setMyProfilePhoto"
        photo = json.dumps(
            {"type": "static", "photo": "attach://avatar"},
            separators=(",", ":"),
        )
        try:
            with path.open("rb") as image:
                response = self.client.post(
                    endpoint,
                    data={"photo": photo},
                    files={"avatar": (path.name, image, "image/jpeg")},
                )
            response.raise_for_status()
            data = response.json()
        except (OSError, httpx.HTTPError, ValueError) as error:
            LOGGER.warning("Telegram profile-photo update failed: %s", type(error).__name__)
            return False
        return isinstance(data, dict) and data.get("ok") is True

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        if not self.customize_bot():
            LOGGER.warning("Telegram bot customization was only partially applied")
        self._prime_offset()
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._poll_loop,
            name="telegram-command-poller",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=12)
        if self._owns_client:
            self.client.close()

    def send_grid(self) -> bool:
        return self._send_message(self._grid_text(), GRID_MARKUP, parse_mode="HTML")

    def handle_update(self, update: dict[str, Any]) -> bool:
        callback = update.get("callback_query")
        if isinstance(callback, dict):
            return self._handle_callback(callback)
        message = update.get("message")
        if not isinstance(message, dict):
            return False
        chat = message.get("chat")
        if not isinstance(chat, dict) or str(chat.get("id", "")) != self.settings.telegram_chat_id:
            return False
        text = str(message.get("text") or "").strip()
        if not text:
            return False
        response, reply_markup, parse_mode = self._response_for(text)
        return self._send_message(response, reply_markup, parse_mode=parse_mode)

    def _response_for(
        self, text: str
    ) -> tuple[str, dict[str, object] | None, str | None]:
        command, argument = _command_parts(text)
        if command in {"/start", "/grid", "grid"}:
            return self._grid_text(), GRID_MARKUP, "HTML"
        if command in {"/status", "📡 pulse", "📡 status"}:
            return self._status_text(), GRID_MARKUP, "HTML"
        if command in {"/new", "🆕 new"}:
            return self._events_text("new", argument), GRID_MARKUP, "HTML"
        if command in {"/ongoing", "🟢 ongoing"}:
            return self._events_text("ongoing", argument), GRID_MARKUP, "HTML"
        if command in {"/soon", "⏰ soon"}:
            return self._events_text("soon", argument), GRID_MARKUP, "HTML"
        if command in {"/latest", "✨ fresh", "🆕 latest"}:
            return self._latest_text(), GRID_MARKUP, "HTML"
        if command in {"/filters", "🎯 filters"}:
            return self._filters_command(argument), GRID_MARKUP, "HTML"
        if command in {"/pause"}:
            return self._set_paused(True), GRID_MARKUP, "HTML"
        if command in {"/resume"}:
            return self._set_paused(False), GRID_MARKUP, "HTML"
        if command in {"⏯ alerts"}:
            return self._set_paused(not self._preferences().paused), GRID_MARKUP, "HTML"
        if command in {"/digest"}:
            return self._digest_command(argument), GRID_MARKUP, "HTML"
        if command in {"🌅 digest"}:
            return self._set_digest(not self._preferences().digest_enabled), GRID_MARKUP, "HTML"
        if command in {"/mute"}:
            return self._mute_command(argument), GRID_MARKUP, "HTML"
        if command in {"/stats", "📈 vault", "📊 stats"}:
            return self._stats_text(), GRID_MARKUP, "HTML"
        if command in {"/sources", "📡 sources", "🌐 coverage", "🛰 sources"}:
            return self._sources_text(), GRID_MARKUP, "HTML"
        if command in {"/help", "🧭 guide", "❓ help"}:
            return _help_text(), GRID_MARKUP, "HTML"
        if command in {"/hide", "⌨️ hide"}:
            return _hidden_text(), REMOVE_GRID_MARKUP, "HTML"
        return _unknown_text(), GRID_MARKUP, "HTML"

    def _grid_text(self) -> str:
        owner_name = escape(self.settings.bot_owner_name)
        source_count = len(self.active_sources)
        return (
            "<b>Hackathon Radar</b>\n"
            f"{owner_name} · {source_count} {_plural(source_count, 'source')} · "
            f"{self.settings.poll_interval_minutes}-min scans\n\n"
            "Choose a view."
        )

    def _status_text(self) -> str:
        total = self.database.total_seen()
        source_count = len(self.active_sources)
        return (
            "<b>Radar online</b>\n"
            f"Every {self.settings.poll_interval_minutes} min · "
            f"{source_count} {_plural(source_count, 'source')} · {total} saved\n"
            f"Next scan within {self.settings.poll_interval_minutes} min"
        )

    def _latest_text(self) -> str:
        items = self.database.recent_seen(limit=MAX_FRESH_ITEMS)
        if not items:
            return "<b>Fresh</b>\nNo opportunities yet."
        cards = [_latest_card(index, item) for index, item in enumerate(items, start=1)]
        return "<b>Fresh</b>\n\n" + "\n".join(cards)

    def _events_text(self, view: str, argument: str) -> str:
        if self.event_store is None:
            return self._latest_text() if view == "new" else _empty_event_text(view)
        limit = _limit(argument, default=10)
        now = self.clock()
        if view == "new":
            events = self.event_store.list_new(limit=limit)
            heading = "New"
        elif view == "ongoing":
            events = self.event_store.list_ongoing(now=now, limit=limit)
            heading = "Ongoing"
        else:
            events = self.event_store.list_soon(now=now, hours=72, limit=limit)
            heading = "Due soon"
        if not events:
            return f"<b>{heading} · 0</b>\nNothing here right now."
        rows = [_event_row(index, event) for index, event in enumerate(events, start=1)]
        return f"<b>{heading} · {len(events)}</b>\n\n" + "\n".join(rows)

    def _stats_text(self) -> str:
        counts = self.database.source_counts()
        if not counts:
            return "<b>Vault · 0 saved</b>\nNo opportunities yet."
        total = self.database.total_seen()
        visible_counts = counts[:MAX_VAULT_SOURCES]
        rows = [f"{escape(source)} · {count}" for source, count in visible_counts]
        hidden_count = len(counts) - len(visible_counts)
        if hidden_count:
            rows.append(f"+{hidden_count} more {_plural(hidden_count, 'source')}")
        return f"<b>Vault · {total} saved</b>\n\n" + "\n".join(rows)

    def _sources_text(self) -> str:
        if self.event_store is not None:
            health = self.event_store.list_source_health()
            if health:
                rows = [_health_row(item, self.active_sources) for item in health]
                healthy = sum(int(item["error_streak"]) == 0 for item in health)
                return f"<b>Sources · {healthy}/{len(health)} healthy</b>\n\n" + "\n".join(rows)
        if not self.active_sources:
            return "<b>Coverage · 0 active</b>\nNo sources enabled."
        rows = _source_rows(self.active_sources)
        return f"<b>Coverage · {len(self.active_sources)} active</b>\n\n{rows}"

    def _filters_command(self, argument: str) -> str:
        if self.event_store is None:
            return "<b>Filters unavailable</b>\nCanonical event storage is not active."
        preferences = self._preferences()
        if argument:
            field, _, raw_value = argument.partition(" ")
            field = field.casefold()
            values = tuple(
                value.strip().casefold() for value in raw_value.split(",") if value.strip()
            )
            if field in {"region", "regions"}:
                preferences = replace(preferences, regions=values)
            elif field in {"stack", "stacks"}:
                preferences = replace(preferences, stacks=values)
            elif field in {"mode", "modes"}:
                preferences = replace(preferences, modes=values)
            elif field == "prize":
                prize = (
                    None
                    if raw_value.casefold() in {"", "off", "none", "0"}
                    else _money(raw_value)
                )
                preferences = replace(preferences, min_prize_usd=prize)
            elif field == "reset":
                preferences = replace(
                    preferences,
                    regions=(),
                    stacks=(),
                    modes=(),
                    min_prize_usd=None,
                    muted_sources=(),
                    muted_domains=(),
                    muted_event_ids=(),
                )
            else:
                return (
                    "<b>Filter not changed</b>\n"
                    "Use region, stack, mode, prize, or reset."
                )
            self._save_preferences(preferences)
        return _filters_text(preferences)

    def _set_paused(self, paused: bool) -> str:
        preferences = replace(self._preferences(), paused=paused)
        self._save_preferences(preferences)
        if paused:
            return "<b>Alerts paused</b>\nScanning continues. Push delivery is off."
        return "<b>Alerts resumed</b>\nNew matches will arrive instantly."

    def _digest_command(self, argument: str) -> str:
        value = argument.casefold()
        if value == "on":
            return self._set_digest(True)
        if value == "off":
            return self._set_digest(False)
        enabled = self._preferences().digest_enabled
        return f"<b>Digest {'on' if enabled else 'off'}</b>\nUse /digest on or /digest off."

    def _set_digest(self, enabled: bool) -> str:
        preferences = replace(self._preferences(), digest_enabled=enabled)
        self._save_preferences(preferences)
        if enabled:
            return "<b>Digest on</b>\nOngoing opportunities will be grouped."
        return "<b>Digest off</b>\nNew and deadline alerts stay instant."

    def _mute_command(self, argument: str) -> str:
        if not argument:
            return "<b>Mute</b>\nUse /mute &lt;event id or domain&gt;."
        preferences = self._preferences()
        target = argument.strip().casefold()
        source = _matching_source(target, self.active_sources)
        if source:
            muted_sources = tuple(dict.fromkeys((*preferences.muted_sources, source.casefold())))
            self._save_preferences(replace(preferences, muted_sources=muted_sources))
            return f"<b>Source muted</b>\n{escape(source)} will no longer alert."
        domain = _domain(target)
        if domain:
            domains = tuple(dict.fromkeys((*preferences.muted_domains, domain)))
            self._save_preferences(replace(preferences, muted_domains=domains))
            return f"<b>Domain muted</b>\n{escape(domain)} will no longer alert."
        event_ids = tuple(dict.fromkeys((*preferences.muted_event_ids, target)))
        self._save_preferences(replace(preferences, muted_event_ids=event_ids))
        if self.event_store is not None:
            self.event_store.mute_event(target)
        return "<b>Event muted</b>\nIt will stay in the archive."

    def _preferences(self) -> UserPreferences:
        if self.event_store is None:
            return UserPreferences()
        return preferences_from_mapping(self.event_store.load_preferences())

    def _save_preferences(self, preferences: UserPreferences) -> None:
        if self.event_store is not None:
            self.event_store.save_preferences(preferences_to_mapping(preferences))

    def _handle_callback(self, callback: dict[str, Any]) -> bool:
        message = callback.get("message")
        chat = message.get("chat") if isinstance(message, dict) else None
        if not isinstance(chat, dict) or str(chat.get("id", "")) != self.settings.telegram_chat_id:
            return False
        if self.event_store is None:
            return False
        data = str(callback.get("data") or "")
        callback_id = str(callback.get("id") or "")
        action, _, event_id = data.partition(":")
        if not callback_id or not event_id:
            return False
        if action == "mute":
            self.event_store.mute_event(event_id)
            preferences = self._preferences()
            muted = tuple(dict.fromkeys((*preferences.muted_event_ids, event_id)))
            self._save_preferences(replace(preferences, muted_event_ids=muted))
            notice = "Muted"
        elif action == "interest":
            self.event_store.mark_interested(event_id)
            notice = "Saved as interested"
        else:
            return False
        return self._api_call(
            "answerCallbackQuery",
            {"callback_query_id": callback_id, "text": notice},
        ) is not None

    def _prime_offset(self) -> None:
        result = self._api_call(
            "getUpdates",
            {
                "offset": -1,
                "limit": 1,
                "timeout": 0,
                "allowed_updates": ["message", "callback_query"],
            },
        )
        if isinstance(result, list) and result:
            self._offset = int(result[-1]["update_id"]) + 1

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            payload: dict[str, object] = {
                "timeout": 10,
                "allowed_updates": ["message", "callback_query"],
            }
            if self._offset is not None:
                payload["offset"] = self._offset
            result = self._api_call("getUpdates", payload)
            if result is None:
                self._stop.wait(5)
                continue
            if not isinstance(result, list):
                LOGGER.warning("Telegram getUpdates returned an unexpected result")
                self._stop.wait(5)
                continue
            for update in result:
                if not isinstance(update, dict):
                    continue
                update_id = update.get("update_id")
                if isinstance(update_id, int):
                    self._offset = update_id + 1
                try:
                    self.handle_update(update)
                except Exception as error:  # command isolation boundary
                    LOGGER.error("Telegram command failed: %s", type(error).__name__)

    def _send_message(
        self,
        text: str,
        reply_markup: dict[str, object] | None,
        *,
        parse_mode: str | None = None,
    ) -> bool:
        payload: dict[str, object] = {
            "chat_id": self.settings.telegram_chat_id,
            "text": _truncate_message(text, 4096),
            "disable_web_page_preview": True,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        if parse_mode is not None:
            payload["parse_mode"] = parse_mode
        return self._api_call("sendMessage", payload) is not None

    def _api_call(self, method: str, payload: dict[str, object]) -> object | None:
        endpoint = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/{method}"
        try:
            response = self.client.post(endpoint, json=payload)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as error:
            LOGGER.warning("Telegram %s failed: %s", method, type(error).__name__)
            return None
        if not isinstance(data, dict) or data.get("ok") is not True:
            LOGGER.warning("Telegram %s returned an unsuccessful response", method)
            return None
        return data.get("result", True)


def _help_text() -> str:
    return (
        "<b>Guide</b>\n"
        "Find · /new · /ongoing · /soon\n"
        "Tune · /filters · /mute\n"
        "Control · /pause · /resume · /digest\n"
        "Health · /sources · /status\n"
        "Grid · /grid · /hide"
    )


def _hidden_text() -> str:
    return "<b>Grid hidden</b>\nAlerts stay on. Send /grid to restore it."


def _unknown_text() -> str:
    return "<b>Unknown command</b>\nChoose a button below."


def _latest_card(index: int, item: dict[str, str]) -> str:
    title = escape(_truncate_inline(item["title"], 96))
    source = escape(item["source"])
    url = item.get("url", "")
    if not url:
        return f"{index}. {title} · {source}"
    safe_url = escape(url, quote=True)
    return f'{index}. <a href="{safe_url}">{title}</a> · {source}'


def _event_row(index: int, event: CanonicalEvent) -> str:
    title = escape(_truncate_inline(event["title"], 72))
    url = escape(event["canonical_url"], quote=True)
    details = [
        _short_date(event["submit_deadline"] or event["reg_deadline"]),
        _display_value(event["mode"]),
        _display_value(event["regions"][0]) if event["regions"] else "",
        _display_value(event["stacks"][0]) if event["stacks"] else "",
    ]
    suffix = " · ".join(item for item in details if item)
    row = f'{index}. <a href="{url}">{title}</a>'
    return f"{row} — {escape(suffix)}" if suffix else row


def _health_row(item: dict[str, Any], active_sources: Sequence[str]) -> str:
    name = _source_display_name(str(item["source"]), active_sources)
    streak = int(item["error_streak"])
    if streak:
        return f"⚠️ {escape(name)} · {streak} {_plural(streak, 'failure')}"
    return f"✅ {escape(name)} · {int(item['event_count'])} found"


def _filters_text(preferences: UserPreferences) -> str:
    muted_count = len(preferences.muted_domains) + len(preferences.muted_event_ids)
    return (
        "<b>Filters</b>\n"
        f"Regions · {_display_values(preferences.regions)}\n"
        f"Stacks · {_display_values(preferences.stacks)}\n"
        f"Modes · {_display_values(preferences.modes)}\n"
        f"Min prize · {_money_text(preferences.min_prize_usd)}\n"
        f"Muted · {muted_count}\n"
        "Edit · /filters region africa,global"
    )


def _command_parts(text: str) -> tuple[str, str]:
    compact = " ".join(text.strip().split())
    head, _, argument = compact.partition(" ")
    command = head.casefold().split("@", 1)[0]
    if not head.startswith("/"):
        command = compact.casefold()
        argument = ""
    return command, argument


def _limit(value: str, *, default: int) -> int:
    try:
        return max(1, min(int(value), 20)) if value else default
    except ValueError:
        return default


def _money(value: str) -> int | None:
    digits = "".join(character for character in value if character.isdigit())
    return int(digits) if digits else None


def _money_text(value: int | None) -> str:
    return "Off" if value is None else f"${value:,}"


def _display_values(values: Sequence[str]) -> str:
    return ", ".join(_display_value(value) for value in values) or "All"


def _display_value(value: str) -> str:
    return value.replace("_", " ").title() if value and value != "unknown" else ""


def _short_date(value: str) -> str:
    try:
        parsed = date.fromisoformat(value[:10])
    except ValueError:
        return ""
    return f"{parsed.day} {parsed.strftime('%b')}"


def _domain(value: str) -> str:
    candidate = value if "://" in value else f"//{value}"
    domain = urlsplit(candidate).netloc.casefold().removeprefix("www.")
    return domain if "." in domain and " " not in domain else ""


def _source_display_name(source: str, active_sources: Sequence[str]) -> str:
    normalized = "".join(character for character in source.casefold() if character.isalnum())
    for name in active_sources:
        candidate = "".join(character for character in name.casefold() if character.isalnum())
        if candidate == normalized:
            return name
    return source.replace("_", " ").title()


def _matching_source(value: str, active_sources: Sequence[str]) -> str:
    normalized = "".join(character for character in value.casefold() if character.isalnum())
    for source in active_sources:
        candidate = "".join(character for character in source.casefold() if character.isalnum())
        if normalized == candidate:
            return source
    return ""


def _empty_event_text(view: str) -> str:
    heading = {"ongoing": "Ongoing", "soon": "Due soon"}.get(view, "New")
    return f"<b>{heading} · 0</b>\nNothing here right now."


def _source_rows(sources: Sequence[str]) -> str:
    rows = []
    for start in range(0, len(sources), SOURCES_PER_LINE):
        row = " · ".join(escape(source) for source in sources[start : start + SOURCES_PER_LINE])
        rows.append(row)
    return "\n".join(rows)


def _truncate_inline(value: str, limit: int) -> str:
    value = " ".join(value.split())
    if len(value) <= limit:
        return value
    return f"{value[: limit - 1].rstrip()}…"


def _truncate_message(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[: limit - 1].rstrip()}…"


def _timeout(seconds: float) -> httpx.Timeout:
    return httpx.Timeout(seconds, connect=seconds, read=seconds, write=seconds, pool=seconds)


def _plural(count: int, singular: str) -> str:
    return singular if count == 1 else f"{singular}s"
