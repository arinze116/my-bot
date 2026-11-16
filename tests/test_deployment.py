from __future__ import annotations

from pathlib import Path

UNIT_FILE = Path("deploy/hackathon-radar.service")


def test_systemd_unit_uses_project_virtualenv_and_environment_file() -> None:
    assert UNIT_FILE.exists(), "production systemd unit file is missing"
    unit = UNIT_FILE.read_text(encoding="utf-8")

    assert "WorkingDirectory=/home/ubuntu/my-bot" in unit
    assert "EnvironmentFile=/home/ubuntu/my-bot/.env" in unit
    assert "ExecStart=/home/ubuntu/my-bot/.venv/bin/python main.py" in unit
    assert "Restart=always" in unit
    assert "RestartSec=10" in unit
