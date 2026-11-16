from __future__ import annotations

import json
import logging
import threading
from collections.abc import Sequence
from html import escape
from pathlib import Path
from typing import Any

import httpx

from config import Settings
from db import Database

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
        ["📡 Pulse", "✨ Fresh"],
        ["📈 Vault", "🌐 Coverage"],
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
        client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings
        self.database = database
        self.active_sources = tuple(active_sources)
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
        command = text.casefold().split("@", 1)[0]
        if command in {"/start", "/grid", "grid"}:
            return self._grid_text(), GRID_MARKUP, "HTML"
        if command in {"/status", "📡 pulse", "📡 status"}:
            return self._status_text(), GRID_MARKUP, "HTML"
        if command in {"/latest", "✨ fresh", "🆕 latest"}:
            return self._latest_text(), GRID_MARKUP, "HTML"
        if command in {"/stats", "📈 vault", "📊 stats"}:
            return self._stats_text(), GRID_MARKUP, "HTML"
        if command in {"/sources", "🌐 coverage", "🛰 sources"}:
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
        if not self.active_sources:
            return "<b>Coverage · 0 active</b>\nNo sources enabled."
        rows = _source_rows(self.active_sources)
        return f"<b>Coverage · {len(self.active_sources)} active</b>\n\n{rows}"

    def _prime_offset(self) -> None:
        result = self._api_call(
            "getUpdates",
            {"offset": -1, "limit": 1, "timeout": 0, "allowed_updates": ["message"]},
        )
        if isinstance(result, list) and result:
            self._offset = int(result[-1]["update_id"]) + 1

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            payload: dict[str, object] = {
                "timeout": 10,
                "allowed_updates": ["message"],
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
        "Pulse — status\n"
        "Fresh — recent opportunities\n"
        "Vault — archive totals\n"
        "Coverage — active sources\n"
        "Hide — remove controls"
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
