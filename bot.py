from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable, Sequence
from datetime import date

import httpx

from config import Settings
from models import Hackathon

TELEGRAM_MESSAGE_LIMIT = 4096
LOGGER = logging.getLogger(__name__)


def format_message(
    hackathon: Hackathon | dict[str, object], *, include_link: bool = True
) -> str:
    raw_description = str(hackathon.get("description") or "")
    for description_limit, detail_limit in ((400, 240), (200, 160), (0, 80), (0, 40)):
        description = _escape_markdown(_truncate(raw_description, description_limit))
        message = _build_message(hackathon, description, detail_limit, include_link=include_link)
        if len(message) <= TELEGRAM_MESSAGE_LIMIT:
            return message
    raise ValueError("Hackathon message cannot fit Telegram's length limit")


def _build_message(
    hackathon: Hackathon | dict[str, object],
    description: str,
    detail_limit: int,
    *,
    include_link: bool,
) -> str:
    title = _escape_markdown(_truncate(str(hackathon["title"]), max(detail_limit, 160)))
    lines = ["🚨 *Radar hit*", "", f"*{title}*", ""]
    lines.extend(_detail_lines(hackathon, detail_limit))
    if description:
        lines.extend(["", "📝 *Brief*", description])
    platform = _escape_markdown(_truncate(str(hackathon["platform"]), detail_limit))
    lines.extend(["", f"🔎 *Source:* {platform}"])
    if include_link:
        url = _escape_link_url(str(hackathon["url"]))
        lines.extend(["", f"[View opportunity ↗]({url})"])
    return "\n".join(lines)


def _detail_lines(hackathon: Hackathon | dict[str, object], detail_limit: int) -> list[str]:
    fields = [
        ("💰", "Prize", _field_value(hackathon, "prize")),
        ("⏳", "Apply by", _format_date(_field_value(hackathon, "deadline"))),
        ("🗓️", "Dates", _date_range(hackathon)),
        ("📍", "Format", _field_value(hackathon, "mode")),
        ("👥", "Team", _field_value(hackathon, "team_size")),
        ("🎟️", "Who can enter", _field_value(hackathon, "eligibility")),
        ("🧰", "Focus", _format_tags(_field_value(hackathon, "tech_tags"))),
    ]
    lines = []
    for icon, label, value in fields:
        if not value:
            continue
        lines.append(f"{icon} *{label}:* {_escape_markdown(_truncate(value, detail_limit))}")
    return lines


def _field_value(hackathon: Hackathon | dict[str, object], key: str) -> str:
    raw_value = hackathon.get(key)
    value = str(raw_value).strip() if raw_value is not None else ""
    return "" if value.casefold() == "not listed" else value


def _format_date(value: str) -> str:
    if not value:
        return ""
    try:
        parsed = date.fromisoformat(value[:10])
    except ValueError:
        return value
    return f"{parsed.day} {parsed.strftime('%b')} {parsed.year}"


def _date_range(hackathon: Hackathon | dict[str, object]) -> str:
    start = _format_date(_field_value(hackathon, "start_date"))
    end = _format_date(_field_value(hackathon, "end_date"))
    if start and end:
        return f"{start} → {end}"
    if start:
        return f"Starts {start}"
    if end:
        return f"Ends {end}"
    return ""


def _format_tags(value: str) -> str:
    return " · ".join(item.strip() for item in value.split(",") if item.strip())


class TelegramClient:
    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.Client | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        self._owns_client = client is None
        self.client = client or httpx.Client(timeout=_timeout(settings.http_timeout_seconds))
        self.sleeper = sleeper

    def send_hackathon(self, hackathon: Hackathon) -> bool:
        reply_markup = {
            "inline_keyboard": [
                [{"text": "View opportunity ↗", "url": str(hackathon["url"])}]
            ]
        }
        return self.send_text(
            format_message(hackathon, include_link=False), reply_markup=reply_markup
        )

    def send_startup_message(self, total: int, active_sources: Sequence[str]) -> bool:
        source_count = len(active_sources)
        text = (
            "🟢 *Radar online*\n\n"
            f"{_escape_markdown(self.settings.bot_owner_name)}, your opportunity watch is active."
            "\n\n"
            f"📡 *Sweep:* every {self.settings.poll_interval_minutes} minutes\n"
            f"🌐 *Coverage:* {source_count} {_plural(source_count, 'source')}\n"
            f"📚 *Vault:* {total} {_plural(total, 'opportunity')}\n\n"
            "New listings that clear the signal filter will land here automatically.\n"
            "Use /grid to open your command desk."
        )
        return self.send_text(text)

    def send_error_message(self, source: str, error: Exception) -> bool:
        safe_source = _escape_markdown(source)
        safe_error = _escape_markdown(str(error)[:500])
        text = (
            "⚠️ *Source check failed*\n\n"
            f"*{safe_source}* did not respond during this sweep. The remaining sources are still "
            f"running.\n\nDetails: {safe_error}"
        )
        return self.send_text(text)

    def send_text(self, text: str, *, reply_markup: dict[str, object] | None = None) -> bool:
        for attempt in range(1, self.settings.telegram_retry_attempts + 1):
            outcome = self._send_once(text, reply_markup)
            if outcome == "success":
                return True
            if outcome == "permanent" or attempt == self.settings.telegram_retry_attempts:
                return False
            self.sleeper(self.settings.telegram_retry_delay_seconds)
        return False

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _send_once(self, text: str, reply_markup: dict[str, object] | None) -> str:
        endpoint = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"
        payload = {
            "chat_id": self.settings.telegram_chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        try:
            response = self.client.post(endpoint, json=payload)
        except httpx.HTTPError as error:
            LOGGER.warning("Telegram network attempt failed: %s", type(error).__name__)
            return "retry"
        if response.status_code == 200:
            try:
                if response.json().get("ok") is True:
                    return "success"
            except (AttributeError, ValueError):
                LOGGER.error("Telegram returned invalid JSON")
                return "permanent"
        if response.status_code == 429 or response.status_code >= 500:
            LOGGER.warning("Telegram retryable response: HTTP %s", response.status_code)
            return "retry"
        LOGGER.error("Telegram permanent response: HTTP %s", response.status_code)
        return "permanent"


class ConsoleNotifier:
    def send_hackathon(self, hackathon: Hackathon) -> bool:
        print(format_message(hackathon))
        return True

    def send_startup_message(self, total: int, active_sources: Sequence[str]) -> bool:
        print(
            f"Radar online: {total} archived; {len(active_sources)} active sources; "
            "dry-run delivery"
        )
        return True

    def send_error_message(self, source: str, error: Exception) -> bool:
        print(f"Source error [{source}]: {type(error).__name__}: {error}")
        return True

    def close(self) -> None:
        return None


def send_hackathon(hackathon: Hackathon) -> bool:
    settings = Settings.from_env()
    settings.validate_telegram()
    client = TelegramClient(settings)
    try:
        return client.send_hackathon(hackathon)
    finally:
        client.close()


def send_startup_message(total: int) -> bool:
    settings = Settings.from_env()
    settings.validate_telegram()
    client = TelegramClient(settings)
    try:
        return client.send_startup_message(total, ())
    finally:
        client.close()


def _timeout(seconds: float) -> httpx.Timeout:
    return httpx.Timeout(seconds, connect=seconds, read=seconds, write=seconds, pool=seconds)


def _escape_markdown(value: str) -> str:
    return re.sub(r"([_*\[\]()`\\])", r"\\\1", value)


def _escape_link_url(value: str) -> str:
    return value.replace("\\", "\\\\").replace(")", "\\)")


def _truncate(value: str, limit: int) -> str:
    value = " ".join(value.split())
    if not value or limit <= 0:
        return ""
    if len(value) <= limit:
        return value
    return f"{value[: limit - 1].rstrip()}…"


def _plural(count: int, singular: str) -> str:
    return singular if count == 1 else f"{singular}s"
