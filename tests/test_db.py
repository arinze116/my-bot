from __future__ import annotations

import hashlib

from db import Database, make_id


def test_make_id_matches_prd_formula() -> None:
    expected = hashlib.sha1(b"example hack|https://example.com/hack").hexdigest()
    assert make_id("Example Hack", "HTTPS://EXAMPLE.COM/HACK") == expected


def test_database_marks_each_id_once(tmp_path) -> None:
    database = Database(tmp_path / "seen.db")
    database.init()

    assert database.mark_seen("abc", "Hack", "Test") is True
    assert database.mark_seen("abc", "Hack", "Test") is False
    assert database.is_seen("abc") is True
    assert database.total_seen() == 1


def test_source_initialization_survives_new_connection(tmp_path) -> None:
    path = tmp_path / "seen.db"
    first = Database(path)
    first.init()
    first.mark_source_initialized("devpost")

    second = Database(path)
    assert second.is_source_initialized("devpost") is True
