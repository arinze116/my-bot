from __future__ import annotations

from pathlib import Path

import pytest

from config import Settings


@pytest.fixture
def settings_factory(tmp_path: Path):
    def build(**overrides: object) -> Settings:
        values: dict[str, object] = {
            "telegram_bot_token": "fake-token-for-tests",
            "telegram_chat_id": "123456",
            "bot_owner_name": "Arinze",
            "twitter_bearer_token": "",
            "twitter_queries": ("hackathon",),
            "database_path": tmp_path / "seen.db",
            "poll_interval_minutes": 20,
            "http_timeout_seconds": 15.0,
            "telegram_retry_attempts": 3,
            "telegram_retry_delay_seconds": 5.0,
            "bootstrap_mode": "notify",
            "debug_mode": False,
            "enabled_devpost": True,
            "enabled_devfolio": True,
            "enabled_dorahacks": True,
            "enabled_ethglobal": True,
            "enabled_mlh": True,
            "enabled_lablab": True,
            "enabled_hackerearth": True,
            "enabled_gitcoin": True,
            "enabled_twitter": True,
        }
        values.update(overrides)
        return Settings(**values)

    return build
