"""Tests for MP3 filename parsing and library loading."""
from pathlib import Path

from playlist import Track, _fallback_title, load_track


def test_fallback_title_splits_artist_and_title():
    artist, title = _fallback_title(Path("/music/Beatles - Yesterday.mp3"))
    assert artist == "Beatles"
    assert title == "Yesterday"


def test_fallback_title_unknown_artist():
    artist, title = _fallback_title(Path("/music/SoloTrack.mp3"))
    assert artist == "Unknown Artist"
    assert title == "SoloTrack"


def test_load_track_uses_filename_when_no_tags(tmp_path):
    mp3 = tmp_path / "Daft Punk - One More Time.mp3"
    mp3.write_bytes(b"not a real mp3")
    track = load_track(mp3)
    assert track.artist == "Daft Punk"
    assert track.title == "One More Time"
    assert isinstance(track, Track)
