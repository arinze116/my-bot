from __future__ import annotations

import sqlite3
import stat
import subprocess
import sys
from datetime import UTC, datetime

import pytest

import database_backup as backup_module
from database_backup import backup_database, restore_database


def _write_value(path, value: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS sample (value TEXT NOT NULL)")
        connection.execute("DELETE FROM sample")
        connection.execute("INSERT INTO sample (value) VALUES (?)", (value,))


def _read_value(path) -> str:
    uri = path.resolve().as_uri() + "?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True) as connection:
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


def test_wal_backup_and_restore_leave_no_snapshot_sidecars(tmp_path) -> None:
    database = tmp_path / "radar.db"
    backup_dir = tmp_path / "backups"
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("CREATE TABLE sample (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sample (value) VALUES ('wanted')")

    backup = backup_database(
        database,
        backup_dir,
        now=datetime(2026, 11, 18, 8, 30, tzinfo=UTC),
    )

    assert sorted(path.name for path in backup_dir.iterdir()) == [backup.name]

    _write_value(database, "current")
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    for suffix in ("-wal", "-shm"):
        database.with_name(database.name + suffix).unlink(missing_ok=True)
    result = restore_database(
        backup,
        database,
        replace=True,
        now=datetime(2026, 11, 18, 9, 0, tzinfo=UTC),
    )

    assert _read_value(database) == "wanted"
    assert result.recovery_path is not None
    sidecars = sorted(
        path.relative_to(tmp_path).as_posix()
        for path in tmp_path.rglob("*")
        if path.is_file() and path.name.endswith(("-wal", "-shm"))
    )
    assert sidecars == []


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


def test_restore_refuses_sidecar_created_during_recovery_backup(tmp_path, monkeypatch) -> None:
    database = tmp_path / "radar.db"
    backup_dir = tmp_path / "backups"
    _write_value(database, "wanted")
    backup = backup_database(database, backup_dir)
    _write_value(database, "current")
    original_create_backup = backup_module._create_backup

    def create_backup_with_racing_writer(*args, **kwargs):
        result = original_create_backup(*args, **kwargs)
        if kwargs["prefix"].endswith("-pre-restore"):
            database.with_name(database.name + "-wal").write_bytes(b"active")
        return result

    monkeypatch.setattr(backup_module, "_create_backup", create_backup_with_racing_writer)

    with pytest.raises(RuntimeError, match="sidecar"):
        restore_database(backup, database, replace=True)

    database.with_name(database.name + "-wal").unlink()
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
