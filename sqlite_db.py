"""Shared SQLite connection setup: WAL mode, busy timeout, optional thread lock."""
import sqlite3
import threading
from pathlib import Path


def open_db(
    path: Path,
    *,
    check_same_thread: bool = True,
) -> tuple[sqlite3.Connection, threading.Lock]:
    """Open a SQLite database with WAL journaling and a per-connection lock.

    WAL mode allows the GUI and playback threads to share one database file
    safely. busy_timeout avoids immediate 'database is locked' errors under
    light concurrent write load.
    """
    conn = sqlite3.connect(path, check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn, threading.RLock()
