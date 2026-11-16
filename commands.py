from __future__ import annotations

import logging
import threading
from collections.abc import Sequence
from typing import Any

import httpx

from config import Settings
from db import Database

LOGGER = logging.getLogger(__name__)

BOT_COMMANDS = (
    {"command": "start", "description": "Open your Radar grid"},
    {"command": "grid", "description": "Show the command grid"},
)

GRID_MARKUP = {
    "keyboard": [
        ["📡 Status", "🆕 Latest"],
        ["📊 Stats", "🛰 Sources"],
        ["❓ Help", "⌨️ Hide"],
    ],
    "resize_keyboard": True,
    "is_persistent": True,
    "input_field_placeholder": "Choose a Radar command",
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
                        "Private hackathon intelligence: high-signal opportunity alerts, "
                        "source coverage, archive stats, and a compact command grid."
                    )
                },
            ),
            (
                "setMyShortDescription",
                {"short_description": "Private hackathon alerts and command grid."},
            ),
            ("setMyCommands", {"commands": list(BOT_COMMANDS)}),
        )
        outcomes = [self._api_call(method, payload) is not None for method, payload in calls]
        return all(outcomes)

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
        return self._send_message(_grid_text(), GRID_MARKUP)

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
        response, reply_markup = self._response_for(text)
        return self._send_message(response, reply_markup)

    def _response_for(self, text: str) -> tuple[str, dict[str, object] | None]:
        command = text.casefold().split("@", 1)[0]
        if command in {"/start", "/grid", "grid"}:
            return _grid_text(), GRID_MARKUP
        if command in {"/status", "📡 status"}:
            return self._status_text(), GRID_MARKUP
        if command in {"/latest", "🆕 latest"}:
            return self._latest_text(), GRID_MARKUP
        if command in {"/stats", "📊 stats"}:
            return self._stats_text(), GRID_MARKUP
        if command in {"/sources", "🛰 sources"}:
            return self._sources_text(), GRID_MARKUP
        if command in {"/help", "❓ help"}:
            return _help_text(), GRID_MARKUP
        if command in {"/hide", "⌨️ hide"}:
            return "Keyboard hidden. Send /grid whenever you want it back.", REMOVE_GRID_MARKUP
        return "That command is not on the Radar grid. Choose a tile below.", GRID_MARKUP

    def _status_text(self) -> str:
        return (
            "🟢 RADAR ONLINE\n\n"
            f"Polling: every {self.settings.poll_interval_minutes} minutes\n"
            f"Archived: {self.database.total_seen()} hackathons\n"
            f"Sources: {len(self.active_sources)} active"
        )

    def _latest_text(self) -> str:
        items = self.database.recent_seen(limit=6)
        if not items:
            return (
                "🆕 LATEST CAPTURES\n\n"
                "No archived hackathons yet. The next poll will populate this view."
            )
        cards = [f"{item['source']} — {_truncate(str(item['title']), 80)}" for item in items]
        return "🆕 LATEST CAPTURES\n\n" + "\n\n".join(cards)

    def _stats_text(self) -> str:
        counts = self.database.source_counts()
        if not counts:
            return "📊 ARCHIVE SNAPSHOT\n\nNo archived hackathons yet."
        rows = [f"{source}: {count}" for source, count in counts]
        rows.append(f"Total: {self.database.total_seen()}")
        return "📊 ARCHIVE SNAPSHOT\n\n" + "\n".join(rows)

    def _sources_text(self) -> str:
        sources = " · ".join(self.active_sources) or "No sources enabled"
        return f"🛰 ACTIVE SOURCES\n\n{sources}"

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

    def _send_message(self, text: str, reply_markup: dict[str, object] | None) -> bool:
        payload: dict[str, object] = {
            "chat_id": self.settings.telegram_chat_id,
            "text": _truncate(text, 4096),
            "disable_web_page_preview": True,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
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


def _grid_text() -> str:
    return (
        "🏆 HACKATHON RADAR\n\n"
        "Your private opportunity command center. Tap a tile below; automatic alerts keep "
        "running in the background."
    )


def _help_text() -> str:
    return (
        "❓ RADAR HELP\n\n"
        "Status checks the worker. Latest shows recent captures. Stats summarizes the archive. "
        "Sources shows current coverage. Hide removes the keyboard; /grid restores it."
    )


def _truncate(value: str, limit: int) -> str:
    value = " ".join(value.split())
    if len(value) <= limit:
        return value
    return f"{value[: limit - 1].rstrip()}…"


def _timeout(seconds: float) -> httpx.Timeout:
    return httpx.Timeout(seconds, connect=seconds, read=seconds, write=seconds, pool=seconds)
