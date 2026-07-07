"""Text-to-speech: synthesize commentary using Microsoft Edge voices (free)."""
import asyncio
import hashlib
import threading
from pathlib import Path
import logging

import edge_tts

from sqlite_db import open_db
from voices import DEFAULT_VOICE, normalize_voice, synthesis_candidates

TTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS tts_cache (
    text_hash TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    audio_path TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# Default when no DJ voice is configured.
VOICE = DEFAULT_VOICE

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
    import logging
    try:
        # Convert rate to Edge TTS format: 1.0 = normal, <1.0 = slower, >1.0 = faster
        rate_str = f"+{int((rate - 1.0) * 100)}%" if rate >= 1.0 else f"-{int(abs(rate - 1.0) * 100)}%"
        communicate = edge_tts.Communicate(text, voice=voice, rate=rate_str)
        
        logging.debug(f"[TTS] Attempting to save audio to: {out_path} with voice: {voice}, rate: {rate_str}")
        await communicate.save(str(out_path))
        logging.debug(f"[TTS] Audio successfully saved to: {out_path}")
    except Exception as e:
        logging.error(f"[TTS] Error during _synthesize_async for text '{text[:50]}...': {e}", exc_info=True)
        raise


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
        self.voice = normalize_voice(voice)
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


    def generate(self, text: str) -> Path | None:
        """Synthesize text to MP3, cache it, return the audio path.

        If the text has been synthesized before, return the cached MP3 path
        without re-synthesizing (instant, reuses Edge's audio).
        Returns Path to audio file, or None if generation failed.
        """
        import time

        candidates = synthesis_candidates(self.voice, self.rate)
        attempts: list[tuple[str, float]] = []

        for voice, rate in candidates:
            attempts.append((voice, rate))
            text_hash = _text_hash(text, voice, rate)
            cached = self._cached_path(text_hash)
            if cached:
                logging.debug(
                    f"[TTS] Returning cached audio for '{text[:50]}...' "
                    f"(voice={voice}, rate={rate}): {cached}"
                )
                return cached

            audio_path = self.cache_dir / f"{text_hash}.mp3"
            if audio_path.exists():
                try:
                    audio_path.unlink()
                except OSError:
                    pass

            try:
                logging.debug(
                    f"[TTS] Synthesizing '{text[:50]}...' with voice={voice}, rate={rate}"
                )
                asyncio.run(_synthesize_async(text, audio_path, voice, rate))
                if audio_path.exists() and audio_path.stat().st_size > 0:
                    self._store(text, text_hash, audio_path)
                    logging.info(f"[TTS] Generated audio with voice={voice}, rate={rate}")
                    return audio_path
                logging.warning(f"[TTS] Synthesis produced empty file with voice={voice}, rate={rate}")
            except Exception as e:
                logging.warning(f"[TTS] Attempt failed for voice={voice}, rate={rate}: {e}", exc_info=True)

            time.sleep(0.25)

        logging.error(f"[TTS] All synthesis attempts failed for text (tried={attempts})")
        return None

    def clean_stale_cache(self, max_age_days: int = 7) -> int:
        """Remove cache entries older than max_age_days and orphaned files.

        Returns the number of entries cleaned.
        """
        import time as time_module
        removed = 0
        with self._db_lock:
            # Remove DB entries older than max_age_days
            rows = self.conn.execute(
                "SELECT text_hash, audio_path FROM tts_cache "
                "WHERE created_at < datetime('now', ?)",
                (f"-{max_age_days} days",),
            ).fetchall()
            for row in rows:
                path = Path(row["audio_path"])
                try:
                    if path.exists():
                        path.unlink()
                except OSError:
                    pass
                self.conn.execute(
                    "DELETE FROM tts_cache WHERE text_hash = ?", (row["text_hash"],)
                )
                removed += 1

            # Remove DB entries whose audio file no longer exists
            orphans = self.conn.execute(
                "SELECT text_hash, audio_path FROM tts_cache"
            ).fetchall()
            for row in orphans:
                if not Path(row["audio_path"]).exists():
                    self.conn.execute(
                        "DELETE FROM tts_cache WHERE text_hash = ?", (row["text_hash"],)
                    )
                    removed += 1

            self.conn.commit()

        # Remove audio files not referenced in DB
        db_paths = set()
        with self._db_lock:
            rows = self.conn.execute("SELECT audio_path FROM tts_cache").fetchall()
            db_paths = {Path(r["audio_path"]) for r in rows}

        for f in self.cache_dir.glob("*.mp3"):
            if f not in db_paths:
                try:
                    f.unlink()
                    removed += 1
                except OSError:
                    pass

        return removed


if __name__ == "__main__":
    gen = TTSGenerator(
        Path(__file__).parent / "data" / "ai_dj.db",
        Path(__file__).parent / "data" / "tts_cache",
    )
    text = "Alright everybody, get ready for a true legend in music history!"
    audio = gen.generate(text)
    print(f"Generated: {audio}")
    print(f"File size: {audio.stat().st_size} bytes")
