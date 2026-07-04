"""Playback controller: encapsulates queue/player logic in a controllable background thread."""
import threading
import time
from pathlib import Path
from queue import Queue

from commentary import CommentaryGenerator
from config import get_config
from content_scheduler import ContentScheduler
from dj_profile import DJProfile
from player import Player
from queue_manager import QueueManager
from tts import TTSGenerator


class PlaybackController:
    """Controls playback in a background thread. Accepts commands via a queue."""

    def __init__(self, music_dir: Path, db_path: Path, tts_cache_dir: Path, dj: DJProfile | None = None, queue_manager: "QueueManager | None" = None):
        self.music_dir = music_dir
        self.db_path = db_path
        self.tts_cache_dir = tts_cache_dir
        self.dj = dj  # Current DJ persona
        self.cfg = get_config()
        self._queue_manager = queue_manager  # Optional: provided by GUI to avoid threading issues

        # State (thread-safe via locks)
        self._lock = threading.Lock()
        self._is_running = False
        self._is_paused = False
        self._current_track = None
        self._up_next = None
        self._upcoming_tracks = []  # List maintained by playback thread for GUI to read
        self._history_tracks = []   # List maintained by playback thread for GUI to read
        self._volume = self.cfg["playback"]["volume"]

        # Pre-rendered between-song content (news/market) ready to play instantly,
        # prepared in the background during the current song to avoid dead air.
        self._ready_content_audio = []   # list of (content_type, Path)
        self._content_lock = threading.Lock()
        self._prep_active = False

        # Command queue: (command, args)
        self.command_queue = Queue()
        self._skip_event = threading.Event()  # Signaled when skip is requested

        # State notification callback (for GUI updates)
        self.on_track_changed = None  # Callable(track, up_next)
        self.on_state_changed = None  # Callable(playing, paused)

        # Background thread
        self._thread = None
        self._player = None  # Reference to player for early stopping

    def start(self) -> None:
        """Start the playback thread."""
        with self._lock:
            if self._is_running:
                return
            self._is_running = True
        self._thread = threading.Thread(target=self._playback_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop playback and the background thread."""
        with self._lock:
            self._is_running = False
        if self._thread:
            self._thread.join(timeout=5)

    def pause(self) -> None:
        """Pause playback (but don't advance queue)."""
        with self._lock:
            self._is_paused = True
        if self._player:
            self._player.pause()
        if self.on_state_changed:
            self.on_state_changed(False, True)

    def resume(self) -> None:
        """Resume playback."""
        with self._lock:
            self._is_paused = False
        if self._player:
            self._player.resume()
        if self.on_state_changed:
            self.on_state_changed(True, False)

    def skip(self) -> None:
        """Skip the current track."""
        self._skip_event.set()
        if self._player:
            self._player.stop()

    def set_volume(self, vol: int) -> None:
        """Set playback volume (0-100)."""
        with self._lock:
            self._volume = max(0, min(100, vol))
        # Apply immediately (libvlc's audio_set_volume is thread-safe) so the
        # slider is responsive, rather than queueing commands that drain slowly.
        if self._player:
            self._player.set_volume(self._volume)

    def get_state(self) -> dict:
        """Get current playback state."""
        with self._lock:
            return {
                "current_track": self._current_track,
                "up_next": self._up_next,
                "volume": self._volume,
                "playing": self._is_running and not self._is_paused,
                "paused": self._is_paused,
            }

    def peek_queue(self, n: int = 10) -> list:
        """Get upcoming tracks from queue (thread-safe copy maintained by playback thread)."""
        with self._lock:
            return self._upcoming_tracks[:n]

    def recently_played(self, n: int = 10) -> list:
        """Get recently played tracks from history (thread-safe copy maintained by playback thread)."""
        with self._lock:
            return self._history_tracks[:n]

    def rate_track(self, track_id: int, rating: int) -> None:
        """Rate current track: -1 (thumbs down), 1 (thumbs up)."""
        if self._queue_manager:
            self._queue_manager.rate_track(track_id, rating)

    def remove_from_queue(self, track_id: int) -> None:
        """Remove a track from the upcoming queue."""
        if self._queue_manager:
            self._queue_manager.remove_from_queue(track_id)

    def requeue_track(self, track_id: int) -> None:
        """Add a track back to the queue (from recently played)."""
        if self._queue_manager:
            self._queue_manager.requeue_track(track_id)

    def _playback_loop(self) -> None:
        """Main playback loop (runs in background thread)."""
        # Always create a new QueueManager in this thread to avoid SQLite thread issues.
        # The queue_manager passed from GUI is only used for thread-safe peek/history access.
        queue = QueueManager(self.db_path, self.music_dir)
        queue.sync_library()
        # Start each session fresh: clear last session's play history, then
        # queue the entire library (otherwise the persisted queue would only
        # hold last session's unplayed tracks).
        queue.clear_history()
        total = queue.rebuild_queue()
        if self.cfg["logging"]["verbose"]:
            print(f"Queued {total} songs from library.")

        dj = CommentaryGenerator(
            self.db_path,
            target_seconds=self.cfg["commentary"]["target_seconds"]
        )
        # Create TTS with DJ's voice and speed settings
        tts_voice = self.dj.voice if self.dj and self.dj.voice else None
        tts_speed = self.dj.speed if self.dj and self.dj.speed else 1.0
        tts = TTSGenerator(self.db_path, self.tts_cache_dir, voice=tts_voice, rate=tts_speed)
        player = Player(volume=self._volume)
        self._player = player

        # News read at its own (calmer) speed so it doesn't inherit a fast DJ
        # music-talk rate. Falls back to 1.0 for DJs created before this field.
        news_speed = (self.dj.news_speed if self.dj and self.dj.news_speed else 1.0)
        news_tts = TTSGenerator(self.db_path, self.tts_cache_dir, voice=tts_voice, rate=news_speed)

        # Resolve the DJ's chosen news sources to actual RSS feeds
        from news_fetcher import feeds_from_sources
        dj_sources = None
        if self.dj and self.dj.news_sources:
            dj_sources = [s.strip() for s in self.dj.news_sources.split(",") if s.strip()]
        news_feeds = feeds_from_sources(dj_sources)

        news_interval = (
            self.cfg["news"]["interval_minutes"]
            if self.cfg["news"]["enabled"]
            else None
        )
        market_time = (
            self.cfg["market"]["time"] if self.cfg["market"]["enabled"] else None
        )
        scheduler = ContentScheduler(
            news_interval_minutes=news_interval,
            market_time=market_time,
            news_target_seconds=self.cfg["news"]["target_seconds"],
            market_target_seconds=self.cfg["market"]["target_seconds"],
            news_feeds=news_feeds,
        )
        scheduler.start()

        try:
            while True:
                with self._lock:
                    if not self._is_running:
                        break

                # Process commands
                try:
                    cmd, arg = self.command_queue.get_nowait()
                    if cmd == "skip":
                        continue  # Skip this track, go to next
                    elif cmd == "set_volume":
                        player.media_player.audio_set_volume(arg)
                except:
                    pass

                # Handle pause
                while True:
                    with self._lock:
                        if not self._is_paused:
                            break
                    time.sleep(0.1)

                # Play any pre-rendered news/market audio prepared during the
                # previous song (already synthesized → instant, no dead air).
                with self._content_lock:
                    ready = self._ready_content_audio
                    self._ready_content_audio = []
                for content_type, audio_path in ready:
                    try:
                        player._play_file(audio_path)
                    except Exception:
                        pass

                # Get next track
                track = queue.advance()
                up_next = queue.peek_queue(1)
                up_next_track = up_next[0] if up_next else None

                # Update upcoming and history lists for GUI (thread-safe)
                upcoming = queue.peek_queue(20)
                history = queue.recently_played(20)

                with self._lock:
                    self._current_track = track
                    self._up_next = up_next_track
                    self._upcoming_tracks = upcoming
                    self._history_tracks = history

                if self.on_track_changed:
                    self.on_track_changed(track, up_next_track)

                # Pre-generate next track's commentary
                if up_next_track and self.cfg["commentary"]["enabled"]:
                    threading.Thread(
                        target=self._pregenerate_commentary,
                        args=(up_next_track, dj, tts),
                        daemon=True,
                    ).start()

                # Generate and play commentary + track. The intro is the DJ's
                # artist commentary followed by an announcement of the song name.
                if self.cfg["commentary"]["enabled"]:
                    try:
                        blurb = dj.get_commentary(track)
                    except Exception:
                        blurb = None
                    intro_text = self._compose_intro(blurb, track)
                else:
                    intro_text = None

                # Play TTS + music with real-time command handling
                try:
                    if intro_text:
                        try:
                            tts_path = tts.generate(intro_text)
                            player.play(tts_path, blocking=False)
                            self._wait_for_playback_end(player)
                        except Exception as e:
                            if self.cfg["logging"]["verbose"]:
                                print(f"TTS playback error: {e}")

                    # Try to play the track, skip if file is missing/unplayable
                    try:
                        player.play(track.path, blocking=False)

                        # While the song plays, prepare the next between-song
                        # content (news/market) in the background so it's ready
                        # to play instantly when the song ends — no dead air.
                        if not self._prep_active:
                            self._prep_active = True
                            threading.Thread(
                                target=self._prepare_between_song_content,
                                args=(scheduler, news_tts),
                                daemon=True,
                            ).start()

                        self._wait_for_playback_end(player)
                        # Track played successfully, update stats
                        queue.mark_played(track.id)
                    except Exception as e:
                        if self.cfg["logging"]["verbose"]:
                            print(f"Track {track.path} unplayable, skipping: {e}")
                        # File is missing or unplayable, skip to next track
                        continue

                except Exception as e:
                    if self.cfg["logging"]["verbose"]:
                        print(f"Playback error: {e}")
                    pass

        except Exception as e:
            print(f"Playback error: {e}")
        finally:
            scheduler.stop()

    def _prepare_between_song_content(self, scheduler, news_tts) -> None:
        """Runs in a background thread during a song. Fetches any pending
        news/market content and pre-synthesizes it to audio so it can play
        instantly between songs (no dead air)."""
        try:
            # If configured, fetch a fresh news brief now (fetch + LLM condense)
            if self.cfg["news"]["enabled"] and self.cfg["news"].get("after_every_song", False):
                if self.cfg["logging"]["verbose"]:
                    print("Pre-fetching news during song...")
                scheduler.fetch_news_now()

            # Drain whatever is pending and synthesize it to audio files
            while scheduler.has_pending():
                content_type, text = scheduler.get_pending()
                try:
                    audio_path = news_tts.generate(text)  # slow synth, happens during song
                    with self._content_lock:
                        self._ready_content_audio.append((content_type, audio_path))
                    if self.cfg["logging"]["verbose"]:
                        print(f"Pre-rendered {content_type} audio ready.")
                except Exception as e:
                    if self.cfg["logging"]["verbose"]:
                        print(f"Content pre-render error: {e}")
        finally:
            self._prep_active = False

    def _wait_for_playback_end(self, player: Player) -> None:
        """Wait for playback to finish while processing real-time commands."""
        while not player.is_finished():
            with self._lock:
                if not self._is_running:
                    player.stop()
                    return

            # Process commands while playback is ongoing
            try:
                cmd, arg = self.command_queue.get_nowait()
                if cmd == "skip":
                    player.stop()
                    return
                elif cmd == "set_volume":
                    player.set_volume(arg)
            except:
                pass

            # Handle pause/resume
            while True:
                with self._lock:
                    if not self._is_paused:
                        break
                time.sleep(0.1)

            if self._is_paused:
                player.pause()
            else:
                player.resume()

            time.sleep(0.1)

    @staticmethod
    def _song_announcement(track) -> str:
        """A short spoken line naming the song, appended after DJ commentary.
        Strips parenthetical content (e.g. '(Remix)') from the title."""
        title = (track.title or "").strip()
        if not title:
            return ""
        # Remove everything from the first opening paren onwards (e.g., '(Remix)')
        if "(" in title:
            title = title[:title.index("(")].strip()
        if not title:
            return ""
        artist = (track.artist or "").strip()
        if artist and not artist.lower().startswith("unknown"):
            return f"This one's called {title}, by {artist}."
        return f"This one's called {title}."

    def _compose_intro(self, blurb, track) -> str | None:
        """Combine the DJ's artist commentary with a song announcement so the
        DJ names the actual track at the end of the intro."""
        announce = self._song_announcement(track)
        if blurb and announce:
            return f"{blurb} {announce}"
        return blurb or announce or None

    def _pregenerate_commentary(self, track, dj, tts) -> None:
        try:
            blurb = dj.get_commentary(track)
            intro = self._compose_intro(blurb, track)
            if intro:
                tts.generate(intro)
        except Exception:
            pass
