from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
ENV_FILE = PROJECT_ROOT / ".env"

DEFAULT_TWITTER_QUERIES = (
    (
        '(hackathon OR "hackathon 2026" OR "online hackathon" OR "virtual hackathon" '
        'OR buildathon OR codeathon OR "bounty hack" OR "prize pool hackathon" '
        'OR ("$" hackathon)) -is:retweet lang:en'
    ),
    (
        '(("register now" OR "applications open" OR "submit by" OR '
        '"join our hackathon" OR "we\'re hosting a hackathon" OR '
        '"open for registration") (hackathon OR buildathon)) -is:retweet lang:en'
    ),
    (
        '("hackathon kicks off" OR "hackathon starts" OR "hackathon weekend" '
        'OR "48-hour hack" OR "24-hour hackathon" OR "week-long hackathon" '
        'OR "builders wanted" OR "call for builders") -is:retweet lang:en'
    ),
    (
        '("Solana hackathon" OR ETHGlobal OR "Base hackathon" OR '
        '"Optimism hackathon" OR "Arbitrum hackathon" OR "Polygon hackathon" '
        'OR "Sui hackathon" OR "Aptos hackathon" OR "Near hackathon" '
        'OR "Cosmos hackathon") -is:retweet lang:en'
    ),
    (
        '("Starknet hackathon" OR "zkSync hackathon" OR "Scroll hackathon" '
        'OR "Celestia hackathon" OR "Filecoin hackathon" OR "Protocol Labs" '
        'OR "Devcon hack" OR ETHDenver OR ETHIndia OR ETHRome) '
        "(hackathon OR buildathon OR builders OR apply OR register) -is:retweet lang:en"
    ),
    (
        '("Africa hackathon" OR "Lagos hackathon" OR "Nigeria hackathon" '
        'OR "Kenya hackathon" OR "Ghana hackathon" OR "LATAM hackathon" '
        'OR "India hackathon" OR "SEA hackathon" OR "EU hackathon" '
        'OR "university hackathon" OR "campus hackathon" OR "student hackathon") '
        "-is:retweet lang:en"
    ),
    (
        '("climate hackathon" OR "healthtech hackathon" OR "fintech hackathon" '
        'OR "AI hackathon" OR "robotics hackathon" OR "open source hackathon") '
        "-is:retweet lang:en"
    ),
    (
        '(("encode club" OR dorahacks OR questbook OR gitcoin OR superteam '
        'OR ("builders grant" hack) OR "luma.com" OR "lu.ma" OR devfolio '
        'OR taikai OR mlh OR hackclub OR eventbrite OR "apply:") '
        "(hackathon OR buildathon OR bounty OR builders OR grant)) -is:retweet lang:en"
    ),
)


@dataclass(frozen=True, slots=True)
class Settings:
    telegram_bot_token: str
    telegram_chat_id: str
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
    enabled_mlh: bool
    enabled_lablab: bool
    enabled_hackerearth: bool
    enabled_gitcoin: bool
    enabled_twitter: bool

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv(ENV_FILE, override=False)
        queries = _split_queries(os.getenv("TWITTER_QUERIES", ""))
        bootstrap_mode = os.getenv("BOOTSTRAP_MODE", "baseline").strip().lower()
        if bootstrap_mode not in {"baseline", "notify"}:
            raise ValueError("BOOTSTRAP_MODE must be 'baseline' or 'notify'")
        return cls(
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
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
