"""Phase 7: configurable radio station with toggles.

Plays through the shuffled queue, synthesizing DJ blurbs via TTS (edge-tts).
On a background schedule (configurable), injects news and market segments
into the playback stream. All settings read from config.yaml or environment.
"""
import sys
import threading
from pathlib import Path

from commentary import CommentaryGenerator
from config import get_config
from content_scheduler import ContentScheduler
from player import Player
from queue_manager import QueueManager
from tts import TTSGenerator

MUSIC_DIR = Path(r"C:\Users\AI\Desktop\mp3s")
DB_PATH = Path(__file__).parent / "data" / "ai_dj.db"
TTS_CACHE_DIR = Path(__file__).parent / "data" / "tts_cache"


def _pregenerate_commentary_tts(track, dj: CommentaryGenerator,
                                tts_gen: TTSGenerator, cfg) -> None:
    """Background thread: generate TTS for a track's commentary (if any)."""
    if not cfg["commentary"]["enabled"]:
        return
    try:
        blurb = dj.get_commentary(track)
        if blurb:
            tts_gen.generate(blurb)
    except Exception:
        pass


def main() -> None:
    cfg = get_config()
    if cfg["logging"]["verbose"]:
        print(f"Config: {cfg}")

    queue = QueueManager(DB_PATH, MUSIC_DIR)
    added = queue.sync_library()
    if added:
        print(f"Added {added} new track(s) to the library.")

    dj = CommentaryGenerator(
        DB_PATH,
        target_seconds=cfg["commentary"]["target_seconds"]
    )
    tts = TTSGenerator(DB_PATH, TTS_CACHE_DIR)
    player = Player(volume=cfg["playback"]["volume"])

    # Start the background scheduler if news/market are enabled
    news_interval = cfg["news"]["interval_minutes"] if cfg["news"]["enabled"] else None
    market_time = cfg["market"]["time"] if cfg["market"]["enabled"] else None
    scheduler = ContentScheduler(
        news_interval_minutes=news_interval,
        market_time=market_time,
        news_target_seconds=cfg["news"]["target_seconds"],
        market_target_seconds=cfg["market"]["target_seconds"],
    )
    scheduler.start()

    try:
        while True:
            # Check for pending news/market content before playing the next track.
            while scheduler.has_pending():
                content_type, text = scheduler.get_pending()
                try:
                    tts_path = tts.generate(text)
                    label = "NEWS" if content_type == "news" else "MARKET"
                    print(f"\n*** {label} UPDATE ***")
                    print(text)
                    player._play_file(tts_path)
                except Exception as e:
                    print(f"  [Failed to play {content_type}: {e}]")

            track = queue.advance()
            up_next = queue.peek_queue(1)

            # Pre-generate TTS for the *next* track if commentary is enabled
            if up_next and cfg["commentary"]["enabled"]:
                bg = threading.Thread(
                    target=_pregenerate_commentary_tts,
                    args=(up_next[0], dj, tts, cfg),
                    daemon=True,
                )
                bg.start()

            # Get commentary if enabled
            if cfg["commentary"]["enabled"]:
                try:
                    blurb = dj.get_commentary(track)
                except Exception as e:
                    blurb = None
                    print(f"  [commentary unavailable: {e}]")
            else:
                blurb = None

            if blurb:
                try:
                    tts_path = tts.generate(blurb)
                    print(f"\n>>> DJ: {blurb}")
                    print(f"Now playing: {track.artist} - {track.title}")
                    if up_next:
                        print(f"  (up next: {up_next[0].artist} - {up_next[0].title})")
                    player.play_tts_then_track(tts_path, track)
                except Exception as e:
                    print(f"  [TTS failed: {e}; skipping to track]")
                    print(f"Now playing: {track.artist} - {track.title}")
                    if up_next:
                        print(f"  (up next: {up_next[0].artist} - {up_next[0].title})")
                    player.play_blocking(track)
            else:
                print(f"Now playing: {track.artist} - {track.title}")
                if up_next:
                    print(f"  (up next: {up_next[0].artist} - {up_next[0].title})")
                player.play_blocking(track)
    except KeyboardInterrupt:
        print("\nStopped.")
        player.stop()
        scheduler.stop()
    except RuntimeError as e:
        print(f"\n{e}")
        scheduler.stop()
        sys.exit(1)


if __name__ == "__main__":
    main()
