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
    return _create_backup(
        Path(database_path),
        Path(output_dir),
        now=now,
        prefix=prefix,
        source_immutable=False,
    )


def _create_backup(
    source: Path,
    destination_dir: Path,
    *,
    now: datetime | None,
    prefix: str,
    source_immutable: bool,
) -> Path:
    if not source.is_file():
        raise FileNotFoundError(source)
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{prefix}-{_stamp(now)}.sqlite3"
    if destination.exists():
        raise FileExistsError(destination)
    temporary = _snapshot(
        source,
        destination_dir,
        destination.name,
        source_immutable=source_immutable,
    )
    try:
        os.link(temporary, destination)
    finally:
        _remove_snapshot(temporary)
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
    _assert_no_sidecars(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    recovery_path = None
    if destination.exists():
        recovery_path = _create_backup(
            destination,
            destination.parent,
            now=now,
            prefix=f"{destination.stem}-pre-restore",
            source_immutable=True,
        )
        _assert_no_sidecars(destination)
    temporary = _snapshot(
        backup,
        destination.parent,
        destination.name,
        source_immutable=True,
    )
    try:
        os.replace(temporary, destination)
    finally:
        _remove_snapshot(temporary)
    return RestoreResult(destination, recovery_path)


def _snapshot(
    source: Path,
    directory: Path,
    name: str,
    *,
    source_immutable: bool,
) -> Path:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{name}.",
        suffix=".tmp",
        dir=directory,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    source_uri = source.resolve().as_uri() + "?mode=ro"
    if source_immutable:
        source_uri += "&immutable=1"
    try:
        with (
            sqlite3.connect(source_uri, uri=True) as source_connection,
            sqlite3.connect(temporary) as destination_connection,
        ):
            source_connection.backup(destination_connection)
            destination_connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        _assert_integrity(temporary)
    except Exception:
        _remove_snapshot(temporary)
        raise
    _remove_sidecars(temporary)
    return temporary


def _assert_integrity(path: Path) -> None:
    uri = path.resolve().as_uri() + "?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True) as connection:
        row = connection.execute("PRAGMA integrity_check").fetchone()
    if row is None or str(row[0]).casefold() != "ok":
        raise sqlite3.DatabaseError(f"SQLite integrity check failed for {path.name}")


def _assert_no_sidecars(path: Path) -> None:
    for sidecar in _sidecars(path):
        if sidecar.exists():
            raise RuntimeError(f"Refusing restore while SQLite sidecar exists: {sidecar.name}")


def _remove_snapshot(path: Path) -> None:
    path.unlink(missing_ok=True)
    _remove_sidecars(path)


def _remove_sidecars(path: Path) -> None:
    for sidecar in _sidecars(path):
        sidecar.unlink(missing_ok=True)


def _sidecars(path: Path) -> tuple[Path, Path]:
    return Path(str(path) + "-wal"), Path(str(path) + "-shm")


def _stamp(value: datetime | None) -> str:
    current = value or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
