"""Playback controller: encapsulates queue/player logic in a controllable background thread."""
import threading
import time
from datetime import datetime # ADDED: Import datetime for use in _prepare_between_song_content
from pathlib import Path
from queue import Empty, Queue

import logging
from commentary import CommentaryGenerator
from config import get_config
from content_scheduler import ContentScheduler
from dj_profile import DJProfile
from player import Player
from playlist import Track # ADDED: Import Track class
from queue_manager import QueueManager
from tts import TTSGenerator
from voices import normalize_voice
from weather import fetch_weather, format_weather_blurb


class PlaybackController:
    """Controls playback in a background thread. Accepts commands via a queue."""

    def __init__(self, music_dir: Path, db_path: Path, tts_cache_dir: Path,
                 dj: DJProfile | None = None,
                 queue_manager: "QueueManager | None" = None):
        self.music_dir = music_dir
        self.db_path = db_path
        self.tts_cache_dir = tts_cache_dir
        self.dj = dj
        self.cfg = get_config()
        self._queue_manager = queue_manager

        self._lock = threading.Lock()
        self._is_running = False
        self._is_paused = False
        self._current_track = None
        self._up_next = None
        self._upcoming_tracks = []
        self._history_tracks = []
        self._volume = self.cfg["playback"]["volume"]
        self._songs_played_count = 0  # Initialize counter for weather frequency

        self._pregenerated_commentary_audio: Path | None = None
        self._pregenerated_commentary_track_id: int | None = None
        self._pregenerated_commentary_lock = threading.Lock()
        self._commentary_ready = threading.Event()

        self._ready_content_audio = []
        self._content_lock = threading.Lock()
        self._prep_active = False

        self.command_queue = Queue()
        self._skip_event = threading.Event()

        self.on_track_changed = None
        self.on_state_changed = None

        self._thread = None
        self._player = None

    def start(self) -> None:
        with self._lock:
            if self._is_running:
                return
            self._is_running = True
        self._thread = threading.Thread(target=self._playback_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._is_running = False
        if self._thread:
            self._thread.join(timeout=5)

    def pause(self) -> None:
        with self._lock:
            self._is_paused = True
        if self._player:
            self._player.pause()
        if self.on_state_changed:
            self.on_state_changed(False, True)

    def resume(self) -> None:
        with self._lock:
            self._is_paused = False
        if self._player:
            self._player.resume()
        if self.on_state_changed:
            self.on_state_changed(True, False)

    def skip(self) -> None:
        # Only stop playback — do not clear pre-generated commentary, which may
        # already be ready for the next track we advance to.
        self._skip_event.set()
        if self._player:
            self._player.stop()

    def set_volume(self, vol: int) -> None:
        with self._lock:
            self._volume = max(0, min(100, vol))
        if self._player:
            self._player.set_volume(self._volume)

    def get_state(self) -> dict:
        with self._lock:
            return {
                "current_track": self._current_track,
                "up_next": self._up_next,
                "volume": self._volume,
                "playing": self._is_running and not self._is_paused,
                "paused": self._is_paused,
            }

    def peek_queue(self, n: int = 10) -> list:
        with self._lock:
            return self._upcoming_tracks[:n]

    def recently_played(self, n: int = 10) -> list:
        with self._lock:
            return self._history_tracks[:n]

    def rate_track(self, track_id: int, rating: int) -> None:
        if self._queue_manager:
            self._queue_manager.rate_track(track_id, rating)

    def remove_from_queue(self, track_id: int) -> None:
        if self._queue_manager:
            self._queue_manager.remove_from_queue(track_id)

    def requeue_track(self, track_id: int) -> None:
        if self._queue_manager:
            self._queue_manager.requeue_track(track_id)

    def _playback_loop(self) -> None:
        """Main playback loop (runs in background thread)."""
        queue = QueueManager(self.db_path, self.music_dir)
        queue.sync_library()
        queue.clear_history()
        total = queue.rebuild_queue()
        if self.cfg["logging"]["verbose"]:
            print(f"Queued {total} songs from library.")

        commentary = CommentaryGenerator(
            self.db_path,
            target_seconds=self.cfg["commentary"]["target_seconds"]
        )
        tts_voice = normalize_voice(self.dj.voice if self.dj and self.dj.voice else None)
        tts_speed = self.dj.speed if self.dj and self.dj.speed else 1.0
        
        commentary_tts = TTSGenerator(self.db_path, self.tts_cache_dir, voice=tts_voice, rate=tts_speed)
        news_tts = TTSGenerator(self.db_path, self.tts_cache_dir, voice=tts_voice, rate=self.dj.news_speed if self.dj else 1.0)
        weather_tts = TTSGenerator(self.db_path, self.tts_cache_dir, voice=tts_voice, rate=self.dj.weather_speed if self.dj else 1.0)
        player = Player(volume=self._volume)
        self._player = player

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
            market_tickers=self.cfg["market"].get("tickers"),
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
                        continue
                    elif cmd == "set_volume":
                        player.media_player.audio_set_volume(arg)
                except Empty:
                    pass
                except Exception as e:
                    logging.debug(f"[PlaybackController] Error processing command: {e}")

                # Handle pause
                while True:
                    with self._lock:
                        if not self._is_paused:
                            break
                    time.sleep(0.1)

                # Play any pre-rendered content (news/market/weather) prepared
                # during the previous song.
                with self._content_lock:
                    ready = self._ready_content_audio
                    self._ready_content_audio = []

                for content_type, audio_path in ready:
                    try:
                        logging.debug(f"[PlaybackController] Playing pre-rendered {content_type} audio: {audio_path}")
                        player._play_file(audio_path)
                        self._wait_for_playback_end(player)
                        logging.debug(f"[PlaybackController] Finished playing {content_type} audio.")
                    except Exception as e:
                        logging.error(f"[PlaybackController] Error playing pre-rendered {content_type} audio: {e}")

                had_preroll_content = bool(ready)

                # Get next track, then play commentary matched to that track.
                track = queue.advance()
                up_next = queue.peek_queue(1)
                up_next_track = up_next[0] if up_next else None

                upcoming = queue.peek_queue(20)
                history = queue.recently_played(20)

                with self._lock:
                    self._current_track = track
                    self._up_next = up_next_track
                    self._upcoming_tracks = upcoming
                    self._history_tracks = history

                if self.on_track_changed:
                    self.on_track_changed(track, up_next_track)

                commentary_audio_to_play = self._resolve_commentary_audio(
                    track,
                    commentary,
                    commentary_tts,
                    had_preroll_content=had_preroll_content,
                )
                if commentary_audio_to_play and self.cfg["commentary"]["enabled"]:
                    try:
                        logging.debug(
                            f"[PlaybackController] Playing commentary for {track.artist}: "
                            f"{commentary_audio_to_play}"
                        )
                        player._play_file(commentary_audio_to_play)
                        self._wait_for_playback_end(player)
                        logging.debug(f"[PlaybackController] Finished commentary for {track.artist}.")
                    except Exception as e:
                        logging.error(f"[PlaybackController] Error playing commentary for {track.artist}: {e}")

                logging.debug(f"Commentary enabled: {self.cfg['commentary']['enabled']}")
                logging.debug(f"Up next track for pre-generation: {up_next_track}")

                # Pre-generate next track's commentary while this one plays.
                if up_next_track and self.cfg["commentary"]["enabled"]:
                    logging.debug(f"Starting commentary pre-generation for {up_next_track.artist}")
                    threading.Thread(
                        target=self._pregenerate_commentary,
                        args=(up_next_track, commentary, commentary_tts),
                        daemon=True,
                    ).start()

                try:
                    player.play(track.path, blocking=False)

                    # While the song plays, prepare next between-song
                    # content (news/market/weather) in the background.
                    if not self._prep_active:
                        self._prep_active = True
                        threading.Thread(
                            target=self._prepare_between_song_content,
                            args=(scheduler, news_tts, weather_tts),
                            daemon=True,
                        ).start()

                    self._wait_for_playback_end(player)
                    queue.mark_played(track.id)
                    self._songs_played_count += 1 # Increment after each song
                except Exception as e:
                    if self.cfg["logging"]["verbose"]:
                        print(f"Track {track.path} unplayable, skipping: {e}")
                    continue

        except Exception as e:
            print(f"Playback error: {e}")
        finally:
            scheduler.stop()

    def _prepare_between_song_content(self, scheduler, news_tts, weather_tts) -> None:
        """Pre-render news/market/weather audio during current song."""
        try:
            # News: fetch if scheduled (after_every_song=true) or if scheduler has pending
            if self.cfg["news"]["enabled"]:
                if self.cfg["news"].get("after_every_song", False):
                    if self.cfg["logging"]["verbose"]:
                        logging.debug("Pre-fetching news during song...")
                    scheduler.fetch_news_now()

            # Drain pending news/market content from scheduler
            consumed = 0
            while scheduler.has_pending():
                pending = scheduler.get_pending()
                if not pending:
                    break
                content_type, text = pending
                try:
                    audio_path = news_tts.generate(text)
                    if audio_path:
                        with self._content_lock:
                            self._ready_content_audio.append((content_type, audio_path))
                        logging.debug(f"[PlaybackController] Pre-rendered {content_type} audio ready: {audio_path}")
                    else:
                        logging.warning(f"[PlaybackController] TTS returned None for {content_type} summary (length={len(text)})")
                    consumed += 1
                except Exception as e:
                    logging.exception(f"[PlaybackController] Content pre-render error for {content_type}: {e}")
            if consumed:
                logging.debug(f"[PlaybackController] Consumed {consumed} scheduled content items")

            # Market data: play at configured time
            if self.cfg["market"]["enabled"]:
                market_time_str = self.cfg["market"]["time"]
                now = datetime.now()
                market_hour, market_minute = map(int, market_time_str.split(":"))
                
                if now.hour == market_hour and now.minute == market_minute:
                    if not hasattr(self, '_market_played_this_minute') or not self._market_played_this_minute:
                        from market_fetcher import get_market_brief
                        market_blurb = get_market_brief(self.cfg["market"]["target_seconds"])
                        if market_blurb:
                            audio_path = news_tts.generate(market_blurb)
                            if audio_path:
                                with self._content_lock:
                                    self._ready_content_audio.append(("market", audio_path))
                        self._market_played_this_minute = True
                else:
                    self._market_played_this_minute = False

            # Weather: play on configured interval (every N songs)
            if self.cfg["weather"]["enabled"] and self.cfg["weather"].get("time_between_songs", False):
                play_every_n = self.cfg["weather"].get("play_every_n_songs", 3)
                if self._songs_played_count > 0 and self._songs_played_count % play_every_n == 0:
                    weather_data = fetch_weather()
                    dj_name = self.dj.stage_name if self.dj else "your DJ"
                    station_name = self.dj.station_name if self.dj else "the airwaves"
                    blurb = format_weather_blurb(weather_data, dj_name, station_name)
                    
                    if blurb:
                        audio_path = weather_tts.generate(blurb)
                        if audio_path:
                            with self._content_lock:
                                self._ready_content_audio.append(("weather", audio_path))
                            logging.debug(f"[PlaybackController] Pre-rendered weather audio ready: {audio_path}")
                        else:
                            logging.warning("[PlaybackController] Weather TTS returned None; skipping weather audio.")

        except Exception as e:
            logging.error(f"Error preparing between song content: {e}")
        finally:
            self._prep_active = False

    def _prepare_weather_blurb(self, weather_tts) -> None:
        """Pre-render weather audio in background."""
        try:
            if self.cfg["weather"]["enabled"] and self.cfg["weather"]["time_between_songs"]:
                weather_data = fetch_weather()
                dj_name = self.dj.stage_name if self.dj else "your DJ"
                station_name = self.dj.station_name if self.dj else "the airwaves"
                blurb = format_weather_blurb(weather_data, dj_name, station_name)

                if blurb:
                    with self._content_lock:
                        self._ready_content_audio.append(("weather", weather_tts.generate(blurb)))
        except Exception as e:
            logging.error(f"Error preparing weather blurb: {e}")

    def _wait_for_playback_end(self, player: Player) -> None:
        """Wait for playback to finish while processing real-time commands."""
        while not player.is_finished():
            with self._lock:
                if not self._is_running:
                    player.stop()
                    return

            try:
                cmd, arg = self.command_queue.get_nowait()
                if cmd == "skip":
                    player.stop()
                    return
                elif cmd == "set_volume":
                    player.set_volume(arg)
            except Empty:
                pass
            except Exception:
                pass

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
        """Extract and clean the song title for announcement."""
        title = (track.title or "").strip()
        if not title:
            return ""
        if "(" in title:
            title = title[:title.index("(")].strip()
        return title

    def _compose_intro(self, blurb: str | None, track: Track, artist_type: str | None, artist_gender: str | None) -> str | None:
        """Compose the full introduction, including blurb and dynamic song announcement."""
        announcement_phrase = ""
        if artist_type == "Person":
            if artist_gender == "Female":
                announcement_phrase = "Here she is with"
            elif artist_gender == "Male":
                announcement_phrase = "Here he is with"
            else: # Unknown gender for a person
                announcement_phrase = "Here they are with"
        elif artist_type == "Group":
            announcement_phrase = "Here they are with"
        else: # Other types or unknown
            announcement_phrase = f"Here's {track.artist} with" # Fallback to include artist name if type is unknown

        song_title = self._song_announcement(track) # Get just the cleaned title

        if song_title and announcement_phrase:
            full_announcement = f"{announcement_phrase} {song_title}."
        elif song_title:
            full_announcement = f"Now playing {song_title}." # Simpler fallback if no specific phrase
        else:
            full_announcement = ""

        if blurb and full_announcement:
            blurb_clean = blurb.rstrip()
            if not blurb_clean.endswith((".", "!", "?")):
                blurb_clean += "."
            # Period + "And" gives TTS a brief pause before the song intro.
            announce = full_announcement[0].lower() + full_announcement[1:]
            return f"{blurb_clean} And {announce}"
        return blurb or full_announcement or None

    def _get_commentary_for_track(
        self, track_id: int, wait_seconds: float = 0.0
    ) -> Path | None:
        """Return pre-generated commentary for track_id, waiting briefly if needed."""
        deadline = time.monotonic() + wait_seconds
        while True:
            with self._pregenerated_commentary_lock:
                if (
                    self._pregenerated_commentary_audio
                    and self._pregenerated_commentary_track_id == track_id
                ):
                    audio = self._pregenerated_commentary_audio
                    self._pregenerated_commentary_audio = None
                    self._pregenerated_commentary_track_id = None
                    self._commentary_ready.clear()
                    return audio
                if (
                    self._pregenerated_commentary_audio
                    and self._pregenerated_commentary_track_id != track_id
                ):
                    logging.debug(
                        "[PlaybackController] Discarding stale commentary for track "
                        f"{self._pregenerated_commentary_track_id} (need {track_id})"
                    )
                    self._pregenerated_commentary_audio = None
                    self._pregenerated_commentary_track_id = None
                    self._commentary_ready.clear()

            if time.monotonic() >= deadline:
                logging.debug(
                    f"[PlaybackController] No commentary ready for track {track_id} "
                    f"after {wait_seconds:.1f}s"
                )
                return None

            remaining = deadline - time.monotonic()
            self._commentary_ready.wait(timeout=min(0.25, max(0.05, remaining)))

    def _store_commentary(self, track: Track, audio_path: Path | None) -> None:
        """Store pre-generated commentary keyed by track id."""
        if not audio_path:
            return
        with self._pregenerated_commentary_lock:
            self._pregenerated_commentary_audio = audio_path
            self._pregenerated_commentary_track_id = track.id
            self._commentary_ready.set()

    def _resolve_commentary_audio(
        self,
        track: Track,
        commentary_gen: CommentaryGenerator,
        tts_commentary: TTSGenerator,
        had_preroll_content: bool = False,
    ) -> Path | None:
        """Wait for background commentary, then fall back to cached sync synthesis."""
        wait_seconds = 15.0 if had_preroll_content else 8.0
        audio = self._get_commentary_for_track(track.id, wait_seconds=wait_seconds)
        if audio:
            logging.info(
                f"[PlaybackController] Using pre-generated commentary for {track.artist}"
            )
            return audio

        if not self.cfg["commentary"]["enabled"]:
            return None

        try:
            logging.info(
                f"[PlaybackController] Generating commentary synchronously for {track.artist}"
            )
            blurb, artist_type, artist_gender = commentary_gen.get_commentary(track)
            intro = self._compose_intro(blurb, track, artist_type, artist_gender)
            if not intro:
                return None
            return tts_commentary.generate(intro)
        except Exception as e:
            logging.error(
                f"[PlaybackController] Sync commentary fallback failed for {track.artist}: {e}"
            )
            return None

    def _pregenerate_commentary(
        self, track: Track, commentary_gen, tts_commentary: TTSGenerator
    ) -> None:
        try:
            blurb, artist_type, artist_gender = commentary_gen.get_commentary(track)
            intro = self._compose_intro(blurb, track, artist_type, artist_gender)
            
            logging.debug(f"[PlaybackController] Pregenerating commentary. Intro text: '{intro}'")
            logging.debug(f"[PlaybackController] TTS Voice: {tts_commentary.voice}, Rate: {tts_commentary.rate}")

            if intro:
                audio_path = tts_commentary.generate(intro)
                self._store_commentary(track, audio_path)
                if audio_path:
                    logging.debug(
                        f"[PlaybackController] Pregenerated commentary for {track.artist}: "
                        f"{intro[:50]}..."
                    )
            else:
                logging.debug(f"[PlaybackController] No commentary blurb for {track.artist}.")
        except Exception as e:
            logging.error(f"Error pre-generating commentary for {track.artist}: {e}")