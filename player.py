"""Thin wrapper around python-vlc for sequential track playback."""
import time
from pathlib import Path

import vlc

from playlist import Track


class Player:
    def __init__(self, volume: int = 80):
        self.instance = vlc.Instance("--no-video")
        self.media_player = self.instance.media_player_new()
        self._volume = max(0, min(100, volume))
        self.media_player.audio_set_volume(self._volume)
        self.is_playing = False
        self._current_media = None

    def play(self, path: Path | str, blocking: bool = False) -> None:
        """Play a file. If blocking=True, wait until done. Otherwise start and return immediately."""
        # Fully stop and release the previous media first. Reusing the player
        # without releasing the old media makes VLC's audio clock drift, which
        # causes playback to progressively speed up over successive clips.
        self.media_player.stop()
        if self._current_media is not None:
            self._current_media.release()
            self._current_media = None

        media = self.instance.media_new(str(path))
        self._current_media = media
        self.media_player.set_media(media)
        # Re-assert volume: a fresh media can reset the audio output volume.
        self.media_player.audio_set_volume(self._volume)
        self.media_player.play()
        time.sleep(0.3)  # let playback start before polling
        self.media_player.audio_set_volume(self._volume)
        self.is_playing = True

        if blocking:
            while True:
                state = self.media_player.get_state()
                if state in (vlc.State.Ended, vlc.State.Error, vlc.State.Stopped):
                    self.is_playing = False
                    break
                time.sleep(0.1)

    def is_finished(self) -> bool:
        """Check if current playback is finished."""
        state = self.media_player.get_state()
        finished = state in (vlc.State.Ended, vlc.State.Error, vlc.State.Stopped)
        if finished:
            self.is_playing = False
        return finished

    def pause(self) -> None:
        """Pause playback."""
        self.media_player.pause()
        self.is_playing = False

    def resume(self) -> None:
        """Resume playback."""
        self.media_player.play()
        self.is_playing = True

    def set_volume(self, vol: int) -> None:
        """Set volume (0-100). Stored so it survives media changes."""
        self._volume = max(0, min(100, vol))
        self.media_player.audio_set_volume(self._volume)

    def stop(self) -> None:
        """Stop playback."""
        self.media_player.stop()
        self.is_playing = False

    def _play_file(self, path: Path | str) -> None:
        """Play a single audio file, blocking until done."""
        self.play(path, blocking=True)

    def play_blocking(self, track: Track) -> None:
        """Play a track, blocking until done."""
        self.play(track.path, blocking=True)

    def play_tts_then_track(self, tts_path: Path, track: Track) -> None:
        """Play TTS commentary, then the song."""
        self._play_file(tts_path)
        self._play_file(track.path)
