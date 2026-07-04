"""Reads a folder of MP3s and extracts ID3 tags into a track list."""
from dataclasses import dataclass
from pathlib import Path
import io

from mutagen.mp3 import MP3
from mutagen.id3 import ID3NoHeaderError, APIC


@dataclass
class Track:
    path: Path
    artist: str
    title: str
    album: str | None
    duration: float | None
    id: int = 0  # Database ID (0 if not from DB)
    album_art: bytes | None = None  # Embedded album art (JPEG/PNG bytes)


def _fallback_title(path: Path) -> tuple[str, str]:
    # Many rips are named "Artist - Title.mp3" with no ID3 tags at all.
    stem = path.stem
    if " - " in stem:
        artist, title = stem.split(" - ", 1)
        return artist.strip(), title.strip()
    return "Unknown Artist", stem


def load_track(path: Path) -> Track:
    # Filenames follow a clean "Artist - Title.mp3" convention; ID3 tags on
    # these files are YouTube-rip artifacts (e.g. artist "FooVEVO", title
    # duplicating the artist name) and are less reliable than the filename.
    artist, title = _fallback_title(path)
    album, duration, album_art = None, None, None
    try:
        audio = MP3(path)
        duration = audio.info.length if audio.info else None
        tags = audio.tags
        if tags:
            if tags.get("TALB"):
                album = str(tags.get("TALB"))
            # Extract embedded album art (APIC frame)
            for key in tags.keys():
                if key.startswith("APIC"):
                    frame = tags[key]
                    if isinstance(frame, APIC):
                        album_art = frame.data
                        break
    except (ID3NoHeaderError, Exception):
        pass
    return Track(
        path=path,
        artist=artist,
        title=title,
        album=album,
        duration=duration,
        album_art=album_art,
    )


def load_library(folder: Path) -> list[Track]:
    mp3_paths = sorted(folder.glob("**/*.mp3"))
    return [load_track(p) for p in mp3_paths]
