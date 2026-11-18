from __future__ import annotations

from pathlib import Path

UNIT_FILE = Path("deploy/hackathon-radar.service")
BACKUP_UNIT_FILE = Path("deploy/hackathon-radar-backup.service")
BACKUP_TIMER_FILE = Path("deploy/hackathon-radar-backup.timer")
OFFSITE_BACKUP_UNIT_FILE = Path("deploy/hackathon-radar-offsite-backup.service")
OFFSITE_BACKUP_TIMER_FILE = Path("deploy/hackathon-radar-offsite-backup.timer")


def test_systemd_unit_uses_project_virtualenv_and_environment_file() -> None:
    assert UNIT_FILE.exists(), "production systemd unit file is missing"
    unit = UNIT_FILE.read_text(encoding="utf-8")

    assert "WorkingDirectory=/home/ubuntu/my-bot" in unit
    assert "EnvironmentFile=/home/ubuntu/my-bot/.env" in unit
    assert "ExecStart=/home/ubuntu/my-bot/.venv/bin/python main.py" in unit
    assert "Restart=always" in unit
    assert "RestartSec=10" in unit


def test_backup_timer_uses_verified_snapshot_cli() -> None:
    assert BACKUP_UNIT_FILE.exists(), "backup systemd unit file is missing"
    assert BACKUP_TIMER_FILE.exists(), "backup systemd timer file is missing"
    unit = BACKUP_UNIT_FILE.read_text(encoding="utf-8")
    timer = BACKUP_TIMER_FILE.read_text(encoding="utf-8")

    assert "WorkingDirectory=/home/ubuntu/my-bot" in unit
    assert "EnvironmentFile=/home/ubuntu/my-bot/.env" in unit
    assert ".venv/bin/python -m scripts.database_backup backup" in unit
    assert "--output-dir /home/ubuntu/my-bot/backups" in unit
    assert "OnCalendar=daily" in timer
    assert "Persistent=true" in timer


def test_offsite_backup_timer_runs_verified_telegram_recovery() -> None:
    assert OFFSITE_BACKUP_UNIT_FILE.exists(), "off-site backup unit file is missing"
    assert OFFSITE_BACKUP_TIMER_FILE.exists(), "off-site backup timer file is missing"
    unit = OFFSITE_BACKUP_UNIT_FILE.read_text(encoding="utf-8")
    timer = OFFSITE_BACKUP_TIMER_FILE.read_text(encoding="utf-8")

    assert "WorkingDirectory=/home/ubuntu/my-bot" in unit
    assert "EnvironmentFile=/home/ubuntu/my-bot/.env" in unit
    assert ".venv/bin/python -m scripts.offsite_backup" in unit
    assert "--catalog /home/ubuntu/my-bot/offsite_backups.json" in unit
    assert "OnCalendar=*-*-* 01:00:00" in timer
    assert "Persistent=true" in timer
