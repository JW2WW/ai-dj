"""SQLite-backed queue: library cache, shuffle rotation, now-playing/history state."""
import random
import sqlite3
from pathlib import Path

from playlist import Track, load_library

SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    artist TEXT NOT NULL,
    title TEXT NOT NULL,
    album TEXT,
    duration REAL,
    last_played_at TEXT,
    play_count INTEGER DEFAULT 0,
    user_rating INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id INTEGER NOT NULL REFERENCES tracks(id),
    position INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id INTEGER NOT NULL REFERENCES tracks(id),
    played_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# How many of the most-recently-played tracks to keep out of the front of a
# fresh shuffle, so the same handful of songs don't loop back-to-back.
NO_REPEAT_WINDOW = 8

# User ratings: -1 = thumbs down (play less), 0 = neutral, 1 = thumbs up (play more)
# Tracks with thumbs down get lower priority in shuffle


class QueueManager:
    def __init__(self, db_path: Path, music_dir: Path):
        self.music_dir = music_dir
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def sync_library(self) -> int:
        """Scan music_dir, add new tracks, and remove entries for deleted files."""
        tracks = load_library(self.music_dir)
        added = 0
        for t in tracks:
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO tracks (path, artist, title, album, duration) "
                "VALUES (?, ?, ?, ?, ?)",
                (str(t.path), t.artist, t.title, t.album, t.duration),
            )
            added += cur.rowcount

        # Remove entries for files that no longer exist
        existing_paths = {str(t.path) for t in tracks}
        all_db_paths = self.conn.execute("SELECT path FROM tracks").fetchall()
        for (db_path,) in all_db_paths:
            if db_path not in existing_paths:
                self.conn.execute("DELETE FROM tracks WHERE path = ?", (db_path,))

        self.conn.commit()
        return added

    def _row_to_track(self, row: sqlite3.Row) -> Track | None:
        if row is None:
            return None
        return Track(
            path=Path(row["path"]),
            artist=row["artist"],
            title=row["title"],
            album=row["album"],
            duration=row["duration"],
            id=row["id"],
        )

    def _recent_track_ids(self, limit: int) -> set[int]:
        rows = self.conn.execute(
            "SELECT track_id FROM history ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return {r["track_id"] for r in rows}

    def _fill_queue(self) -> None:
        all_rows = self.conn.execute(
            "SELECT id, user_rating FROM tracks ORDER BY id"
        ).fetchall()
        if not all_rows:
            return

        # Separate tracks by rating: thumbs-down (avoid), neutral, thumbs-up (prefer)
        thumbs_down = [r["id"] for r in all_rows if r["user_rating"] == -1]
        neutral = [r["id"] for r in all_rows if r["user_rating"] == 0]
        thumbs_up = [r["id"] for r in all_rows if r["user_rating"] == 1]

        recent = self._recent_track_ids(min(NO_REPEAT_WINDOW, len(all_rows) - 1))

        # Separate recent/fresh from each rating tier
        fresh_up = [i for i in thumbs_up if i not in recent]
        recent_up = [i for i in thumbs_up if i in recent]
        fresh_neutral = [i for i in neutral if i not in recent]
        recent_neutral = [i for i in neutral if i in recent]
        fresh_down = [i for i in thumbs_down if i not in recent]

        # Shuffle within each tier
        random.shuffle(fresh_up)
        random.shuffle(fresh_neutral)
        random.shuffle(fresh_down)
        random.shuffle(recent_up)
        random.shuffle(recent_neutral)

        # Order: fresh favored → fresh neutral → fresh downvoted → recent (at back)
        ordered = fresh_up + fresh_neutral + fresh_down + recent_up + recent_neutral

        self.conn.executemany(
            "INSERT INTO queue (track_id, position) VALUES (?, ?)",
            [(track_id, pos) for pos, track_id in enumerate(ordered)],
        )
        self.conn.commit()

    def clear_history(self) -> None:
        """Wipe play history. Called at startup so a fresh session doesn't carry
        over last session's recently-played list."""
        self.conn.execute("DELETE FROM history")
        self.conn.commit()

    def rebuild_queue(self) -> int:
        """Clear the queue and re-enqueue the entire library, freshly shuffled.

        Called at startup so every song is queued each run — otherwise the
        persisted queue would only contain last session's unplayed tracks.
        Returns the number of tracks queued.
        """
        self.conn.execute("DELETE FROM queue")
        self.conn.commit()
        self._fill_queue()
        row = self.conn.execute("SELECT COUNT(*) FROM queue").fetchone()
        return row[0] if row else 0

    def peek_queue(self, n: int = 5) -> list[Track]:
        rows = self.conn.execute(
            "SELECT tracks.* FROM queue JOIN tracks ON queue.track_id = tracks.id "
            "ORDER BY queue.position LIMIT ?",
            (n,),
        ).fetchall()
        return [self._row_to_track(r) for r in rows]

    def current(self) -> Track | None:
        row = self.conn.execute(
            "SELECT tracks.* FROM history JOIN tracks ON history.track_id = tracks.id "
            "ORDER BY history.id DESC LIMIT 1"
        ).fetchone()
        return self._row_to_track(row) if row else None

    def recently_played(self, n: int = 10) -> list[Track]:
        rows = self.conn.execute(
            "SELECT tracks.* FROM history JOIN tracks ON history.track_id = tracks.id "
            "ORDER BY history.id DESC LIMIT ?",
            (n,),
        ).fetchall()
        return [self._row_to_track(r) for r in rows]

    def advance(self) -> Track:
        """Pop the next track off the queue, record it in history, return it.
        Refills and reshuffles the queue automatically when it runs dry.
        Skips tracks that have been deleted from the library."""
        while True:
            if not self.conn.execute("SELECT 1 FROM queue LIMIT 1").fetchone():
                self._fill_queue()

            row = self.conn.execute(
                "SELECT id, track_id FROM queue ORDER BY position LIMIT 1"
            ).fetchone()
            if row is None:
                raise RuntimeError("Library is empty — no tracks to queue.")

            self.conn.execute("DELETE FROM queue WHERE id = ?", (row["id"],))
            self.conn.execute(
                "INSERT INTO history (track_id) VALUES (?)", (row["track_id"],)
            )
            self.conn.commit()

            track_row = self.conn.execute(
                "SELECT * FROM tracks WHERE id = ?", (row["track_id"],)
            ).fetchone()
            track = self._row_to_track(track_row)
            if track is not None:
                return track

    # "Skip" is just "advance" from the caller's perspective — the player
    # stops the current track and asks the queue for the next one.
    skip = advance

    def remove_from_queue(self, track_id: int) -> None:
        """Remove a track from the upcoming queue (doesn't delete it, just dequeues it)."""
        self.conn.execute("DELETE FROM queue WHERE track_id = ?", (track_id,))
        self.conn.commit()

    def requeue_track(self, track_id: int) -> None:
        """Add a track back to the front of the queue (for 'replay' from history)."""
        max_pos = self.conn.execute("SELECT MAX(position) FROM queue").fetchone()[0]
        next_pos = (max_pos or -1) + 1
        self.conn.execute(
            "INSERT INTO queue (track_id, position) VALUES (?, ?)",
            (track_id, next_pos),
        )
        self.conn.commit()

    def rate_track(self, track_id: int, rating: int) -> None:
        """Rate a track: -1 (thumbs down), 0 (neutral), 1 (thumbs up)."""
        rating = max(-1, min(1, rating))  # Clamp to [-1, 0, 1]
        self.conn.execute(
            "UPDATE tracks SET user_rating = ? WHERE id = ?",
            (rating, track_id),
        )
        self.conn.commit()

    def mark_played(self, track_id: int) -> None:
        """Update last_played_at and play_count when a track finishes."""
        self.conn.execute(
            "UPDATE tracks SET last_played_at = datetime('now'), play_count = play_count + 1 WHERE id = ?",
            (track_id,),
        )
        self.conn.commit()
