"""Tests for shared SQLite connection setup."""
from pathlib import Path

from sqlite_db import open_db


def test_open_db_enables_wal_mode(tmp_path):
    db_path = tmp_path / "test.db"
    conn, lock = open_db(db_path)
    with lock:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"
