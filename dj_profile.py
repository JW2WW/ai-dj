"""DJ profile system: create, store, and manage DJ personas."""
import json
import sqlite3
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from sqlite_db import open_db

# TTS voice mapping: (gender, generation, orientation) -> (voice_name, tone, speed)
# Tone: "enthusiastic", "calm", "energetic", "smooth", "professional"
# Speed: 0.8 to 1.5 (0.8 = slower, 1.5 = faster)
VOICE_PROFILES = {
    ("male", "boomer", "straight"): ("GuyNeural", "professional", 0.9),
    ("male", "boomer", "gay"): ("GuyNeural", "calm", 0.9),
    ("male", "gen_x", "straight"): ("GuyNeural", "smooth", 1.0),
    ("male", "gen_x", "gay"): ("GuyNeural", "energetic", 1.05),
    ("male", "millennial", "straight"): ("GuyNeural", "energetic", 1.1),
    ("male", "millennial", "gay"): ("GuyNeural", "enthusiastic", 1.15),
    ("male", "gen_z", "straight"): ("GuyNeural", "enthusiastic", 1.2),
    ("male", "gen_z", "gay"): ("GuyNeural", "energetic", 1.25),
    ("male", "alpha", "straight"): ("GuyNeural", "energetic", 1.3),
    ("male", "alpha", "gay"): ("GuyNeural", "enthusiastic", 1.3),
    ("female", "boomer", "straight"): ("AriaNeural", "calm", 0.9),
    ("female", "boomer", "gay"): ("AriaNeural", "calm", 0.85),
    ("female", "gen_x", "straight"): ("AriaNeural", "smooth", 1.0),
    ("female", "gen_x", "gay"): ("AriaNeural", "energetic", 1.05),
    ("female", "millennial", "straight"): ("AriaNeural", "enthusiastic", 1.1),
    ("female", "millennial", "gay"): ("AriaNeural", "energetic", 1.15),
    ("female", "gen_z", "straight"): ("AriaNeural", "energetic", 1.2),
    ("female", "gen_z", "gay"): ("AriaNeural", "enthusiastic", 1.25),
    ("female", "alpha", "straight"): ("AriaNeural", "enthusiastic", 1.3),
    ("female", "alpha", "gay"): ("AriaNeural", "energetic", 1.3),
    ("nonbinary", "boomer", "any"): ("AmberNeural", "calm", 0.95),
    ("nonbinary", "gen_x", "any"): ("AmberNeural", "smooth", 1.0),
    ("nonbinary", "millennial", "any"): ("AmberNeural", "energetic", 1.1),
    ("nonbinary", "gen_z", "any"): ("AmberNeural", "enthusiastic", 1.2),
    ("nonbinary", "alpha", "any"): ("AmberNeural", "enthusiastic", 1.3),
}

# Available Edge TTS voices
AVAILABLE_VOICES = [
    "en-US-AriaNeural",      # Female, neutral
    "en-US-AmberNeural",     # Female, warm
    "en-US-AshleyNeural",    # Female, soft
    "en-US-CoraNeural",      # Female, bright
    "en-US-ElizabethNeural", # Female, calm
    "en-US-JennyNeural",     # Female, natural
    "en-US-MonicaNeural",    # Female, professional
    "en-US-GuyNeural",       # Male, neutral
    "en-US-ArthurNeural",    # Male, calm
    "en-US-BrianNeural",     # Male, friendly
    "en-US-JacobNeural",     # Male, young
]

DJ_DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS djs (
    id TEXT PRIMARY KEY,
    stage_name TEXT NOT NULL,
    station_name TEXT NOT NULL,
    gender TEXT NOT NULL,
    sexual_orientation TEXT NOT NULL,
    music_genre TEXT NOT NULL,
    generation TEXT NOT NULL,
    image_path TEXT,
    voice TEXT,
    tone TEXT,
    speed REAL,
    news_sources TEXT,
    news_speed REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


@dataclass
class DJProfile:
    """A DJ persona with voice and style settings."""
    id: str  # Unique identifier (slug: "morning-mike", "night-nina", etc.)
    stage_name: str  # "Morning Mike", "Night Nina"
    station_name: str  # "WKRP 97.5 FM", "The Groove Room"
    gender: str  # "male", "female", "nonbinary"
    sexual_orientation: str  # "straight", "gay", "lesbian", "bi", "pan", "asexual", "other"
    music_genre: str  # "classic rock", "pop", "hip-hop", "country", "jazz", etc.
    generation: str  # "boomer", "gen_x", "millennial", "gen_z", "alpha"
    image_path: Optional[str] = None  # Path to DJ's profile image
    voice: Optional[str] = None  # TTS voice (e.g., "en-US-GuyNeural")
    tone: Optional[str] = None  # Speech tone (e.g., "energetic")
    speed: Optional[float] = None  # Speech speed (0.8-1.5)
    news_sources: Optional[str] = None  # Comma-separated source names (e.g. "CNN,BBC")
    news_speed: Optional[float] = 1.0  # Speech speed for news reads (default: calmer 1.0)

    def auto_assign_voice(self) -> None:
        """Auto-assign voice, tone, and speed based on demographics."""
        key = (self.gender, self.generation, self.sexual_orientation)
        if key in VOICE_PROFILES:
            voice_base, tone, speed = VOICE_PROFILES[key]
        else:
            # Fallback for unmapped combinations
            voice_base, tone, speed = VOICE_PROFILES.get(
                (self.gender, self.generation, "any"),
                ("AriaNeural", "calm", 1.0),
            )
        self.voice = f"en-US-{voice_base}"
        self.tone = tone
        self.speed = speed

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON storage."""
        return asdict(self)


class DJManager:
    """Manage DJ profiles: create, load, save, list."""

    def __init__(self, db_path: Path, dj_images_dir: Path | None = None):
        self.db_path = db_path
        self.dj_images_dir = dj_images_dir or Path(__file__).parent / "data" / "dj_images"
        self.dj_images_dir.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self.conn, self._lock = open_db(db_path, check_same_thread=False)
        with self._lock:
            self.conn.executescript(DJ_DB_SCHEMA)
            self._migrate()
            self.conn.commit()

    def _migrate(self) -> None:
        """Add newer columns to an existing djs table if they're missing."""
        existing = {row[1] for row in self.conn.execute("PRAGMA table_info(djs)")}
        if "news_sources" not in existing:
            self.conn.execute("ALTER TABLE djs ADD COLUMN news_sources TEXT")
        if "news_speed" not in existing:
            self.conn.execute("ALTER TABLE djs ADD COLUMN news_speed REAL")

    def create_dj(self, profile: DJProfile) -> None:
        """Create and save a new DJ profile."""
        if not profile.voice:
            profile.auto_assign_voice()

        with self._lock:
            self.conn.execute(
                """INSERT OR REPLACE INTO djs
                   (id, stage_name, station_name, gender, sexual_orientation,
                    music_genre, generation, image_path, voice, tone, speed,
                    news_sources, news_speed)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    profile.id,
                    profile.stage_name,
                    profile.station_name,
                    profile.gender,
                    profile.sexual_orientation,
                    profile.music_genre,
                    profile.generation,
                    profile.image_path,
                    profile.voice,
                    profile.tone,
                    profile.speed,
                    profile.news_sources,
                    profile.news_speed,
                ),
            )
            self.conn.commit()

    def get_dj(self, dj_id: str) -> DJProfile | None:
        """Load a DJ profile by ID."""
        with self._lock:
            cursor = self.conn.execute(
                "SELECT id, stage_name, station_name, gender, sexual_orientation, "
                "music_genre, generation, image_path, voice, tone, speed, "
                "news_sources, news_speed FROM djs WHERE id = ?",
                (dj_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            cols = [desc[0] for desc in cursor.description]
            data = dict(zip(cols, row))
            return DJProfile(**data)

    def list_djs(self) -> list[DJProfile]:
        """List all DJ profiles. Auto-create defaults if database is empty."""
        with self._lock:
            cursor = self.conn.execute(
                "SELECT id, stage_name, station_name, gender, sexual_orientation, "
                "music_genre, generation, image_path, voice, tone, speed, "
                "news_sources, news_speed FROM djs ORDER BY stage_name"
            )
            rows = cursor.fetchall()

            if not rows:
                for dj in DEFAULT_DJS:
                    if not dj.voice:
                        dj.auto_assign_voice()
                    self.create_dj(dj)
                cursor = self.conn.execute(
                    "SELECT id, stage_name, station_name, gender, sexual_orientation, "
                    "music_genre, generation, image_path, voice, tone, speed, "
                    "news_sources, news_speed FROM djs ORDER BY stage_name"
                )
                rows = cursor.fetchall()

            cols = [desc[0] for desc in cursor.description]
            return [DJProfile(**dict(zip(cols, row))) for row in rows]

    def delete_dj(self, dj_id: str) -> None:
        """Delete a DJ profile."""
        with self._lock:
            self.conn.execute("DELETE FROM djs WHERE id = ?", (dj_id,))
            self.conn.commit()


# Default demo DJs to get started
DEFAULT_DJS = [
    DJProfile(
        id="morning_mike",
        stage_name="Morning Mike",
        station_name="KPWR 105.9 FM",
        gender="male",
        sexual_orientation="straight",
        music_genre="classic rock",
        generation="gen_x",
        voice="en-US-BrianNeural",  # Friendly, upbeat morning voice
        tone="enthusiastic",
        speed=1.05,
    ),
    DJProfile(
        id="night_nina",
        stage_name="Night Nina",
        station_name="The Groove Room",
        gender="female",
        sexual_orientation="lesbian",
        music_genre="pop",
        generation="millennial",
        voice="en-US-CoraNeural",  # Bright, confident evening voice
        tone="energetic",
        speed=1.1,
    ),
    DJProfile(
        id="sunny_sam",
        stage_name="Sunny Sam",
        station_name="KPOP 99.5 FM",
        gender="nonbinary",
        sexual_orientation="pan",
        music_genre="hip-hop",
        generation="gen_z",
        voice="en-US-JacobNeural",  # Young, contemporary voice
        tone="enthusiastic",
        speed=1.2,
    ),
]


if __name__ == "__main__":
    # Demo: create and list DJs
    mgr = DJManager(Path("data/ai_dj.db"))

    for dj in DEFAULT_DJS:
        dj.auto_assign_voice()
        mgr.create_dj(dj)
        print(f"Created: {dj.stage_name} at {dj.station_name}")
        print(f"  Voice: {dj.voice}, Tone: {dj.tone}, Speed: {dj.speed}")

    print("\nAll DJs:")
    for dj in mgr.list_djs():
        print(f"  {dj.stage_name} ({dj.id})")
