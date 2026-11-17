from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
ENV_FILE = PROJECT_ROOT / ".env"

DEFAULT_TWITTER_QUERIES = (
    "hackathon registration open apply now",
    "hackathon submissions open deadline",
    "join our hackathon register now",
    "hackathon announcement prize pool",
    "web3 hackathon open registration",
    "AI hackathon apply deadline",
    "blockchain hackathon prize winners",
)


@dataclass(frozen=True, slots=True)
class Settings:
    telegram_bot_token: str
    telegram_chat_id: str
    bot_owner_name: str
    twitter_bearer_token: str
    twitter_queries: tuple[str, ...]
    database_path: Path
    poll_interval_minutes: int
    http_timeout_seconds: float
    telegram_retry_attempts: int
    telegram_retry_delay_seconds: float
    bootstrap_mode: str
    debug_mode: bool
    enabled_devpost: bool
    enabled_devfolio: bool
    enabled_dorahacks: bool
    enabled_ethglobal: bool
    enabled_mlh: bool
    enabled_lablab: bool
    enabled_hackerearth: bool
    enabled_gitcoin: bool
    enabled_twitter: bool

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv(ENV_FILE, override=False)
        project_env = dotenv_values(ENV_FILE) if ENV_FILE.is_file() else {}
        queries = _split_queries(os.getenv("TWITTER_QUERIES", ""))
        bootstrap_mode = os.getenv("BOOTSTRAP_MODE", "baseline").strip().lower()
        if bootstrap_mode not in {"baseline", "notify"}:
            raise ValueError("BOOTSTRAP_MODE must be 'baseline' or 'notify'")
        return cls(
            telegram_bot_token=_project_telegram_value(project_env, "TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=_project_telegram_value(project_env, "TELEGRAM_CHAT_ID"),
            bot_owner_name=os.getenv("BOT_OWNER_NAME", "Chinweuba").strip() or "Chinweuba",
            twitter_bearer_token=os.getenv("TWITTER_BEARER_TOKEN", "").strip(),
            twitter_queries=queries or DEFAULT_TWITTER_QUERIES,
            database_path=Path(os.getenv("DATABASE_PATH", "seen_hackathons.db")),
            poll_interval_minutes=_positive_int("POLL_INTERVAL_MINUTES", 20),
            http_timeout_seconds=_bounded_float("HTTP_TIMEOUT_SECONDS", 15.0, maximum=20.0),
            telegram_retry_attempts=_positive_int("TELEGRAM_RETRY_ATTEMPTS", 3),
            telegram_retry_delay_seconds=_positive_float("TELEGRAM_RETRY_DELAY_SECONDS", 5.0),
            bootstrap_mode=bootstrap_mode,
            debug_mode=_bool_env("DEBUG_MODE", False),
            enabled_devpost=_bool_env("ENABLE_DEVPOST", True),
            enabled_devfolio=_bool_env("ENABLE_DEVFOLIO", True),
            enabled_dorahacks=_bool_env("ENABLE_DORAHACKS", True),
            enabled_ethglobal=_bool_env("ENABLE_ETHGLOBAL", True),
            enabled_mlh=_bool_env("ENABLE_MLH", True),
            enabled_lablab=_bool_env("ENABLE_LABLAB", True),
            enabled_hackerearth=_bool_env("ENABLE_HACKEREARTH", True),
            enabled_gitcoin=_bool_env("ENABLE_GITCOIN", True),
            enabled_twitter=_bool_env("ENABLE_TWITTER", True),
        )

    def validate_telegram(self) -> None:
        missing = []
        if not self.telegram_bot_token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not self.telegram_chat_id:
            missing.append("TELEGRAM_CHAT_ID")
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def _positive_int(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _positive_float(name: str, default: float) -> float:
    value = float(os.getenv(name, str(default)))
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _bounded_float(name: str, default: float, *, maximum: float) -> float:
    value = _positive_float(name, default)
    if value > maximum:
        raise ValueError(f"{name} must be no more than {maximum:g}")
    return value


def _split_queries(raw: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in raw.split("||") if item.strip())


def _project_telegram_value(project_env: Mapping[str, str | None], name: str) -> str:
    if ENV_FILE.is_file():
        return str(project_env.get(name) or "").strip()
    return os.getenv(name, "").strip()
