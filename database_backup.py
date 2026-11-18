from __future__ import annotations

import os
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RestoreResult:
    database_path: Path
    recovery_path: Path | None


def backup_database(
    database_path: str | Path,
    output_dir: str | Path,
    *,
    now: datetime | None = None,
    prefix: str = "hackathon-radar",
) -> Path:
    source = Path(database_path)
    if not source.is_file():
        raise FileNotFoundError(source)
    destination_dir = Path(output_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{prefix}-{_stamp(now)}.sqlite3"
    if destination.exists():
        raise FileExistsError(destination)
    temporary = _snapshot(source, destination_dir, destination.name)
    try:
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def restore_database(
    backup_path: str | Path,
    database_path: str | Path,
    *,
    replace: bool = False,
    now: datetime | None = None,
) -> RestoreResult:
    backup = Path(backup_path)
    destination = Path(database_path)
    if not backup.is_file():
        raise FileNotFoundError(backup)
    _assert_integrity(backup)
    if destination.exists() and not replace:
        raise FileExistsError(destination)
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(destination) + suffix)
        if sidecar.exists():
            raise RuntimeError(f"Refusing restore while SQLite sidecar exists: {sidecar.name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    recovery_path = None
    if destination.exists():
        recovery_path = backup_database(
            destination,
            destination.parent,
            now=now,
            prefix=f"{destination.stem}-pre-restore",
        )
    temporary = _snapshot(backup, destination.parent, destination.name)
    try:
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return RestoreResult(destination, recovery_path)


def _snapshot(source: Path, directory: Path, name: str) -> Path:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{name}.",
        suffix=".tmp",
        dir=directory,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with (
            sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True) as source_connection,
            sqlite3.connect(temporary) as destination_connection,
        ):
            source_connection.backup(destination_connection)
        _assert_integrity(temporary)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return temporary


def _assert_integrity(path: Path) -> None:
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        row = connection.execute("PRAGMA integrity_check").fetchone()
    if row is None or str(row[0]).casefold() != "ok":
        raise sqlite3.DatabaseError(f"SQLite integrity check failed for {path.name}")


def _stamp(value: datetime | None) -> str:
    current = value or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
