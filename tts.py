"""Text-to-speech: synthesize commentary using Microsoft Edge voices (free)."""
import asyncio
import hashlib
import sqlite3
import threading
from pathlib import Path

import edge_tts

from sqlite_db import open_db

TTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS tts_cache (
    text_hash TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    audio_path TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# Edge TTS voices; pick one. Common choices:
# - "en-US-GuyNeural" (male, neutral)
# - "en-US-AriaNeural" (female, friendly)
# - "en-US-JennyNeural" (female, natural)
VOICE = "en-US-AriaNeural"


def _text_hash(text: str, voice: str = "", rate: float = 1.0) -> str:
    """Hash text (plus voice/rate) for cache lookups.

    Voice and rate are included so the same words spoken by different DJs or
    at different speeds don't collide to the same cached audio file.
    """
    key = f"{text}|{voice}|{rate}"
    return hashlib.sha256(key.encode()).hexdigest()[:12]


async def _synthesize_async(text: str, out_path: Path, voice: str, rate: float = 1.0) -> None:
    """Generate MP3 audio from text using Edge TTS (requires event loop).

    Args:
        text: The text to synthesize
        out_path: Where to save the MP3
        voice: Edge TTS voice name (e.g., "en-US-AriaNeural")
        rate: Speech rate multiplier (0.5 = half speed, 2.0 = double speed)
    """
    # Convert rate to Edge TTS format: 1.0 = normal, <1.0 = slower, >1.0 = faster
    rate_str = f"+{int((rate - 1.0) * 100)}%" if rate >= 1.0 else f"{int((rate - 1.0) * 100)}%"
    communicate = edge_tts.Communicate(text, voice=voice, rate=rate_str)
    await communicate.save(str(out_path))


class TTSGenerator:
    def __init__(self, db_path: Path, cache_dir: Path, voice: str | None = None, rate: float = 1.0):
        """Initialize TTS generator with optional voice customization.

        Args:
            db_path: Path to cache database
            cache_dir: Directory for cached audio files
            voice: TTS voice name (default: VOICE constant)
            rate: Speech rate multiplier (default: 1.0)
        """
        self.db_path = db_path
        self.cache_dir = cache_dir
        self.voice = voice or VOICE
        self.rate = rate
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.conn, self._db_lock = open_db(db_path, check_same_thread=False)
        with self._db_lock:
            self.conn.executescript(TTS_SCHEMA)
            self.conn.commit()

    def _cached_path(self, text_hash: str) -> Path | None:
        """Return cached audio path if it exists and the file is present."""
        with self._db_lock:
            row = self.conn.execute(
                "SELECT audio_path FROM tts_cache WHERE text_hash = ?", (text_hash,)
            ).fetchone()
            if row:
                path = Path(row[0])
                if path.exists():
                    return path
                # Stale cache entry — file was deleted.
                self.conn.execute("DELETE FROM tts_cache WHERE text_hash = ?",
                                (text_hash,))
                self.conn.commit()
        return None

    def _store(self, text: str, text_hash: str, audio_path: Path) -> None:
        """Record a newly-synthesized audio file in the cache."""
        with self._db_lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO tts_cache (text_hash, text, audio_path) "
                "VALUES (?, ?, ?)",
                (text_hash, text, str(audio_path)),
            )
            self.conn.commit()

    def generate(self, text: str) -> Path:
        """Synthesize text to MP3, cache it, return the audio path.

        If the text has been synthesized before, return the cached MP3 path
        without re-synthesizing (instant, reuses Edge's audio).
        """
        text_hash = _text_hash(text, self.voice, self.rate)
        cached = self._cached_path(text_hash)
        if cached:
            return cached

        # Generate: file naming uses hash for uniqueness + brevity.
        audio_path = self.cache_dir / f"{text_hash}.mp3"
        asyncio.run(_synthesize_async(text, audio_path, self.voice, self.rate))
        self._store(text, text_hash, audio_path)
        return audio_path


if __name__ == "__main__":
    gen = TTSGenerator(
        Path(__file__).parent / "data" / "ai_dj.db",
        Path(__file__).parent / "data" / "tts_cache",
    )
    text = "Alright everybody, get ready for a true legend in music history!"
    audio = gen.generate(text)
    print(f"Generated: {audio}")
    print(f"File size: {audio.stat().st_size} bytes")
