from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable, Sequence

import httpx

from config import Settings
from models import Hackathon

TELEGRAM_MESSAGE_LIMIT = 4096
LOGGER = logging.getLogger(__name__)


def format_message(hackathon: Hackathon | dict[str, object]) -> str:
    tags = _tag_list(str(hackathon.get("tech_tags", "")))
    raw_description = str(hackathon.get("description", ""))
    for description_limit, detail_limit in ((400, 240), (200, 160), (0, 80), (0, 40)):
        description = _escape_markdown(_truncate(raw_description, description_limit))
        message = _build_message(hackathon, description, tags, detail_limit)
        if len(message) <= TELEGRAM_MESSAGE_LIMIT:
            return message
    raise ValueError("Hackathon message cannot fit Telegram's length limit")


def _build_message(
    hackathon: Hackathon | dict[str, object],
    description: str,
    tags: list[str],
    detail_limit: int,
) -> str:
    lines = ["🏆 *NEW HACKATHON DETECTED*", ""]
    lines.extend(_detail_lines(hackathon, detail_limit))
    if description:
        lines.extend(["", f"📝 {description}"])
    url = _escape_link_url(str(hackathon["url"]))
    lines.extend(["", f"🔗 [Apply / View Hackathon]({url})"])
    if tags:
        lines.extend(["", " ".join(f"#{tag}" for tag in tags[:5])])
    return "\n".join(lines)


def _detail_lines(hackathon: Hackathon | dict[str, object], detail_limit: int) -> list[str]:
    fields = (
        ("📌", "Name", "title"),
        ("🏷️", "Platform", "platform"),
        ("💰", "Prize Pool", "prize"),
        ("📅", "Start Date", "start_date"),
        ("🏁", "End Date", "end_date"),
        ("⏰", "Deadline", "deadline"),
        ("🌍", "Mode", "mode"),
        ("🛠️", "Tech / Tags", "tech_tags"),
        ("👥", "Team Size", "team_size"),
        ("🎯", "Eligibility", "eligibility"),
    )
    lines = []
    for icon, label, key in fields:
        value = str(hackathon.get(key) or "Not listed")
        limit = max(detail_limit, 160) if key == "title" else detail_limit
        lines.append(f"{icon} *{label}:* {_escape_markdown(_truncate(value, limit))}")
    return lines


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
        return self.send_text(format_message(hackathon))

    def send_startup_message(self, total: int, active_sources: Sequence[str]) -> bool:
        sources = ", ".join(active_sources) or "none"
        text = (
            "🟢 *Hackathon Radar is live*\n\n"
            f"Active sources: {_escape_markdown(sources)}\n"
            f"Archived hackathons: {total}"
        )
        return self.send_text(text)

    def send_error_message(self, source: str, error: Exception) -> bool:
        safe_source = _escape_markdown(source)
        safe_error = _escape_markdown(str(error)[:500])
        text = f"⚠️ *Hackathon Radar source error*\n\n{safe_source}: {safe_error}"
        return self.send_text(text)

    def send_text(self, text: str) -> bool:
        for attempt in range(1, self.settings.telegram_retry_attempts + 1):
            outcome = self._send_once(text)
            if outcome == "success":
                return True
            if outcome == "permanent" or attempt == self.settings.telegram_retry_attempts:
                return False
            self.sleeper(self.settings.telegram_retry_delay_seconds)
        return False

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _send_once(self, text: str) -> str:
        endpoint = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"
        payload = {
            "chat_id": self.settings.telegram_chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
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
        print(f"Hackathon Radar dry run: {total} archived; sources={', '.join(active_sources)}")
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


def _tag_list(value: str) -> list[str]:
    tags = []
    for item in value.split(","):
        tag = re.sub(r"[^A-Za-z0-9_]", "", item.replace(" ", "_"))
        if tag and tag not in tags:
            tags.append(tag[:40])
    return tags


def _truncate(value: str, limit: int) -> str:
    value = " ".join(value.split())
    if not value or limit <= 0:
        return ""
    if len(value) <= limit:
        return value
    return f"{value[: limit - 1].rstrip()}…"
