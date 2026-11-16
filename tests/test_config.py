from __future__ import annotations

import pytest

from config import Settings


def test_http_timeout_cannot_exceed_system_rule(monkeypatch) -> None:
    monkeypatch.setenv("HTTP_TIMEOUT_SECONDS", "21")

    with pytest.raises(ValueError, match="no more than 20"):
        Settings.from_env()
