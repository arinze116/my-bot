from __future__ import annotations

from pathlib import Path

import pytest

import config
from config import Settings


def test_http_timeout_cannot_exceed_system_rule(monkeypatch) -> None:
    monkeypatch.setenv("HTTP_TIMEOUT_SECONDS", "21")

    with pytest.raises(ValueError, match="no more than 20"):
        Settings.from_env()


def test_settings_uses_project_telegram_token_over_ambient(monkeypatch, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TELEGRAM_BOT_TOKEN=project-bot-token\nTELEGRAM_CHAT_ID=project-chat-id\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "ENV_FILE", env_file)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "ambient-codex-agent-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "ambient-chat-id")

    settings = Settings.from_env()

    assert settings.telegram_bot_token == "project-bot-token"
    assert settings.telegram_chat_id == "project-chat-id"
