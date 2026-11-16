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


def test_database_exposes_recent_items_and_source_counts(tmp_path) -> None:
    database = Database(tmp_path / "seen.db")
    database.init()
    database.mark_seen("1", "First Hack", "Devpost")
    database.mark_seen("2", "Second Hack", "Devpost")
    database.mark_seen("3", "Web3 Sprint", "X/Twitter")

    assert database.recent_seen(limit=2) == [
        {"title": "Web3 Sprint", "source": "X/Twitter"},
        {"title": "Second Hack", "source": "Devpost"},
    ]
    assert database.source_counts() == [("Devpost", 2), ("X/Twitter", 1)]
