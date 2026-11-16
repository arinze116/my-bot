from __future__ import annotations

import hashlib
import os
import sqlite3
from collections.abc import Iterable
from pathlib import Path

from models import Hackathon

SEEN_SCHEMA = """
CREATE TABLE IF NOT EXISTS seen (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

SOURCE_STATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS source_state (
    source TEXT PRIMARY KEY,
    initialized_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(SEEN_SCHEMA)
            connection.execute(SOURCE_STATE_SCHEMA)

    def is_seen(self, uid: str) -> bool:
        with self._connect() as connection:
            row = connection.execute("SELECT 1 FROM seen WHERE id = ?", (uid,)).fetchone()
        return row is not None

    def mark_seen(self, uid: str, title: str, source: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO seen (id, title, source) VALUES (?, ?, ?)",
                (uid, title, source),
            )
        return cursor.rowcount == 1

    def mark_many_seen(self, hackathons: Iterable[Hackathon]) -> int:
        records = [
            (make_id(item["title"], item["url"]), item["title"], item["platform"])
            for item in hackathons
        ]
        if not records:
            return 0
        with self._connect() as connection:
            before = connection.total_changes
            connection.executemany(
                "INSERT OR IGNORE INTO seen (id, title, source) VALUES (?, ?, ?)", records
            )
            return connection.total_changes - before

    def total_seen(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) FROM seen").fetchone()
        return int(row[0])

    def recent_seen(self, *, limit: int = 6) -> list[dict[str, str]]:
        safe_limit = max(1, min(limit, 20))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT title, source FROM seen ORDER BY seen_at DESC, rowid DESC LIMIT ?",
                (safe_limit,),
            ).fetchall()
        return [{"title": str(title), "source": str(source)} for title, source in rows]

    def source_counts(self) -> list[tuple[str, int]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT source, COUNT(*) AS total FROM seen "
                "GROUP BY source ORDER BY total DESC, source ASC"
            ).fetchall()
        return [(str(source), int(total)) for source, total in rows]

    def is_source_initialized(self, source: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM source_state WHERE source = ?", (source,)
            ).fetchone()
        return row is not None

    def mark_source_initialized(self, source: str) -> None:
        with self._connect() as connection:
            connection.execute("INSERT OR IGNORE INTO source_state (source) VALUES (?)", (source,))

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0, check_same_thread=False)
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection


def make_id(title: str, url: str) -> str:
    value = f"{title.lower()}|{url.lower()}".encode()
    return hashlib.sha1(value).hexdigest()  # noqa: S324 - non-security identity hash


_default_database: Database | None = None


def _default_db() -> Database:
    global _default_database
    if _default_database is None:
        _default_database = Database(os.getenv("DATABASE_PATH", "seen_hackathons.db"))
    return _default_database


def init_db() -> None:
    _default_db().init()


def is_seen(uid: str) -> bool:
    return _default_db().is_seen(uid)


def mark_seen(uid: str, title: str, source: str) -> bool:
    return _default_db().mark_seen(uid, title, source)


def total_seen() -> int:
    return _default_db().total_seen()
