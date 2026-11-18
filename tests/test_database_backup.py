from __future__ import annotations

import sqlite3
import stat
import subprocess
import sys
from datetime import UTC, datetime

import pytest

from database_backup import backup_database, restore_database


def _write_value(path, value: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS sample (value TEXT NOT NULL)")
        connection.execute("DELETE FROM sample")
        connection.execute("INSERT INTO sample (value) VALUES (?)", (value,))


def _read_value(path) -> str:
    with sqlite3.connect(path) as connection:
        row = connection.execute("SELECT value FROM sample").fetchone()
    return str(row[0])


def test_backup_is_consistent_and_does_not_overwrite_existing_file(tmp_path) -> None:
    database = tmp_path / "radar.db"
    output_dir = tmp_path / "backups"
    _write_value(database, "current")

    backup = backup_database(
        database,
        output_dir,
        now=datetime(2026, 11, 18, 8, 30, 0, 123456, tzinfo=UTC),
    )

    assert backup.name == "hackathon-radar-20261118T083000.123456Z.sqlite3"
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600
    assert _read_value(backup) == "current"
    with pytest.raises(FileExistsError):
        backup_database(
            database,
            output_dir,
            now=datetime(2026, 11, 18, 8, 30, 0, 123456, tzinfo=UTC),
        )


def test_restore_requires_explicit_replace_and_preserves_recovery_copy(tmp_path) -> None:
    database = tmp_path / "radar.db"
    backup_dir = tmp_path / "backups"
    _write_value(database, "wanted")
    backup = backup_database(
        database,
        backup_dir,
        now=datetime(2026, 11, 18, 8, 30, tzinfo=UTC),
    )
    _write_value(database, "current")

    with pytest.raises(FileExistsError):
        restore_database(backup, database)

    result = restore_database(
        backup,
        database,
        replace=True,
        now=datetime(2026, 11, 18, 9, 0, tzinfo=UTC),
    )

    assert _read_value(database) == "wanted"
    assert result.recovery_path is not None
    assert result.recovery_path.exists()
    assert _read_value(result.recovery_path) == "current"


def test_restore_refuses_existing_wal_sidecar(tmp_path) -> None:
    database = tmp_path / "radar.db"
    backup_dir = tmp_path / "backups"
    _write_value(database, "wanted")
    backup = backup_database(database, backup_dir)
    _write_value(database, "current")
    sidecar = tmp_path / "radar.db-wal"
    sidecar.write_bytes(b"active")

    with pytest.raises(RuntimeError, match="sidecar"):
        restore_database(backup, database, replace=True)

    assert _read_value(database) == "current"


def test_backup_cli_uses_database_path_and_reports_created_snapshot(tmp_path) -> None:
    database = tmp_path / "radar.db"
    output_dir = tmp_path / "backups"
    _write_value(database, "cli")

    result = subprocess.run(  # noqa: S603 - fixed interpreter and repository module
        [
            sys.executable,
            "-m",
            "scripts.database_backup",
            "backup",
            "--database",
            str(database),
            "--output-dir",
            str(output_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    snapshot = output_dir / result.stdout.strip().split("/")[-1]
    assert snapshot.exists()
    assert _read_value(snapshot) == "cli"
