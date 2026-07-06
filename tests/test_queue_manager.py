"""Tests for queue shuffle, ratings, and history."""
from pathlib import Path

from queue_manager import QueueManager


def _make_library(tmp_path: Path, count: int = 5):
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    for i in range(count):
        (music_dir / f"Artist {i} - Song {i}.mp3").write_bytes(b"fake")
    return music_dir


def test_sync_library_adds_tracks(tmp_path):
    music_dir = _make_library(tmp_path, 3)
    db_path = tmp_path / "test.db"
    qm = QueueManager(db_path, music_dir)
    added = qm.sync_library()
    assert added == 3
    tracks = qm.list_tracks()
    assert len(tracks) == 3


def test_rebuild_queue_orders_thumbs_up_first(tmp_path):
    music_dir = _make_library(tmp_path, 4)
    db_path = tmp_path / "test.db"
    qm = QueueManager(db_path, music_dir)
    qm.sync_library()
    tracks = qm.list_tracks()
    qm.rate_track(tracks[0].id, 1)
    qm.rebuild_queue()
    upcoming = qm.peek_queue(4)
    assert upcoming[0].id == tracks[0].id


def test_advance_records_history(tmp_path):
    music_dir = _make_library(tmp_path, 2)
    db_path = tmp_path / "test.db"
    qm = QueueManager(db_path, music_dir)
    qm.sync_library()
    qm.rebuild_queue()
    played = qm.advance()
    history = qm.recently_played(1)
    assert history[0].id == played.id


def test_rate_track_clamps_values(tmp_path):
    music_dir = _make_library(tmp_path, 1)
    db_path = tmp_path / "test.db"
    qm = QueueManager(db_path, music_dir)
    qm.sync_library()
    track_id = qm.list_tracks()[0].id
    qm.rate_track(track_id, 99)
    with qm._lock:
        row = qm.conn.execute(
            "SELECT user_rating FROM tracks WHERE id = ?", (track_id,)
        ).fetchone()
    assert row["user_rating"] == 1
