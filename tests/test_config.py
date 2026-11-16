from __future__ import annotations

from pathlib import Path

import pytest

import config
from config import Settings


def test_http_timeout_cannot_exceed_system_rule(monkeypatch) -> None:
    monkeypatch.setenv("HTTP_TIMEOUT_SECONDS", "21")

    with pytest.raises(ValueError, match="no more than 20"):
        Settings.from_env()


def test_settings_loads_project_dotenv_without_overriding_environment(monkeypatch) -> None:
    calls: list[tuple[Path, bool]] = []
    expected_path = Path("test.env")

    def fake_load_dotenv(path: Path, *, override: bool) -> None:
        calls.append((path, override))

    monkeypatch.setattr(config, "ENV_FILE", expected_path, raising=False)
    monkeypatch.setattr(config, "load_dotenv", fake_load_dotenv, raising=False)

    Settings.from_env()

    assert calls == [(expected_path, False)]
