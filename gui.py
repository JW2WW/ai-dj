"""GUI application: system tray icon + control panel for AI DJ."""
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from PIL import Image, ImageDraw
import pystray

from config import get_config
from dj_profile import DJProfile
from playback_controller import PlaybackController

MUSIC_DIR = Path(r"C:\Users\AI\Desktop\mp3s")
DB_PATH = Path(__file__).parent / "data" / "ai_dj.db"
TTS_CACHE_DIR = Path(__file__).parent / "data" / "tts_cache"


def create_icon():
    """Create a simple tray icon (AI DJ in blue)."""
    size = 64
    img = Image.new("RGB", (size, size), color="white")
    draw = ImageDraw.Draw(img)
    # Draw a simple music note
    draw.ellipse([10, 40, 25, 55], fill="blue")
    draw.line([20, 40, 20, 10], fill="blue", width=3)
    draw.ellipse([30, 30, 45, 45], fill="blue")
    draw.line([37, 30, 37, 5], fill="blue", width=3)
    return img


class AIdjGUI:
    def __init__(self, root, dj: DJProfile | None = None):
        self.root = root
        self.dj = dj
        self.root.title(f"AI DJ — {dj.stage_name}" if dj else "AI DJ")
        self.root.geometry("500x450")
        self.root.resizable(False, False)

        self.cfg = get_config()
        self.controller = PlaybackController(MUSIC_DIR, DB_PATH, TTS_CACHE_DIR, dj=dj)
        self.controller.on_track_changed = self._on_track_changed

        # Setup UI
        self._setup_ui()

        # Start playback in background
        self.controller.start()

        # Now set the slider value (after controller is running, so volume changes work)
        self.volume_slider.set(self.cfg["playback"]["volume"])

        # Handle window close -> minimize to tray
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Setup system tray
        self._setup_tray()

    def _setup_ui(self):
        """Build the main window UI."""
        # DJ Info (if selected)
        if self.dj:
            dj_info = ttk.Label(
                self.root,
                text=f"{self.dj.stage_name} — {self.dj.station_name}",
                font=("Arial", 12, "bold"),
                foreground="blue",
            )
            dj_info.pack(pady=5)
            genre_info = ttk.Label(
                self.root,
                text=f"{self.dj.music_genre.title()} • {self.dj.generation.replace('_', ' ').title()}",
                font=("Arial", 9),
                foreground="gray",
            )
            genre_info.pack(pady=2)

        # Now Playing
        now_label = ttk.Label(
            self.root,
            text="Now Playing:",
            font=("Arial", 10, "bold"),
        )
        now_label.pack(pady=(10, 2))

        # Now Playing
        self.now_playing = ttk.Label(
            self.root,
            text="Loading...",
            font=("Arial", 12),
            foreground="blue",
        )
        self.now_playing.pack(pady=5)

        # Up Next
        self.up_next = ttk.Label(
            self.root,
            text="Up next: ...",
            font=("Arial", 10),
            foreground="gray",
        )
        self.up_next.pack(pady=2)

        # Playback controls frame
        controls = ttk.Frame(self.root)
        controls.pack(pady=15)

        self.play_btn = ttk.Button(
            controls,
            text="⏸ Pause",
            command=self._on_pause_click,
        )
        self.play_btn.pack(side=tk.LEFT, padx=5)

        ttk.Button(controls, text="⏭ Skip", command=self._on_skip_click).pack(
            side=tk.LEFT, padx=5
        )

        # Volume control
        vol_frame = ttk.Frame(self.root)
        vol_frame.pack(pady=10, fill=tk.X, padx=20)

        ttk.Label(vol_frame, text="Volume:").pack(side=tk.LEFT)

        # Create label BEFORE slider so callback has it available
        self.volume_label = ttk.Label(vol_frame, text=f"{self.cfg['playback']['volume']}%")

        self.volume_slider = ttk.Scale(
            vol_frame,
            from_=0,
            to=100,
            orient=tk.HORIZONTAL,
            command=self._on_volume_change,
        )
        # Don't set the value here - it triggers callback before controller is running
        # Instead, set it after controller starts (see bottom of __init__)
        self.volume_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)

        self.volume_label.pack(side=tk.LEFT)

        # Settings button
        ttk.Button(self.root, text="⚙ Settings", command=self._on_settings).pack(
            pady=10
        )

        # Status bar
        self.status = ttk.Label(
            self.root,
            text="Playing...",
            font=("Arial", 9),
            foreground="green",
        )
        self.status.pack(pady=5, side=tk.BOTTOM)

    def _setup_tray(self):
        """Create system tray icon and menu."""
        icon = pystray.Icon(
            "AI DJ",
            create_icon(),
            menu=pystray.Menu(
                pystray.MenuItem("Show", self._on_tray_show),
                pystray.MenuItem("Pause", self._on_pause_click),
                pystray.MenuItem("Skip", self._on_skip_click),
                pystray.MenuItem("Exit", self._on_tray_exit),
            ),
        )

        # Run tray icon in a background thread
        def run_tray():
            icon.run()

        tray_thread = threading.Thread(target=run_tray, daemon=True)
        tray_thread.start()
        self.tray_icon = icon

    def _on_track_changed(self, track, up_next):
        """Called by controller when track changes."""
        self.root.after(0, lambda: self._update_track_display(track, up_next))

    def _update_track_display(self, track, up_next):
        """Update now playing and up next displays."""
        self.now_playing.config(text=f"Now: {track.artist} - {track.title}")
        if up_next:
            self.up_next.config(text=f"Up next: {up_next.artist} - {up_next.title}")

    def _on_pause_click(self):
        """Toggle pause/resume."""
        state = self.controller.get_state()
        if state["playing"]:
            self.controller.pause()
            self.play_btn.config(text="▶ Resume")
            self.status.config(text="Paused")
        else:
            self.controller.resume()
            self.play_btn.config(text="⏸ Pause")
            self.status.config(text="Playing...")

    def _on_skip_click(self):
        """Skip to next track."""
        self.controller.skip()
        self.status.config(text="Skipping...")

    def _on_volume_change(self, value):
        """Handle volume slider changes."""
        vol = int(float(value))
        self.volume_label.config(text=f"{vol}%")
        self.controller.set_volume(vol)

    def _on_settings(self):
        """Open settings window."""
        settings_win = tk.Toplevel(self.root)
        settings_win.title("Settings")
        settings_win.geometry("400x300")

        ttk.Label(settings_win, text="Configuration", font=("Arial", 12, "bold")).pack(
            pady=10
        )

        # Commentary
        ttk.Label(settings_win, text="Commentary:").pack(anchor=tk.W, padx=20)
        self.commentary_enabled = tk.BooleanVar(
            value=self.cfg["commentary"]["enabled"]
        )
        ttk.Checkbutton(
            settings_win,
            text="Enabled",
            variable=self.commentary_enabled,
        ).pack(anchor=tk.W, padx=40)

        # News
        ttk.Label(settings_win, text="News:").pack(anchor=tk.W, padx=20, pady=(10, 0))
        self.news_enabled = tk.BooleanVar(value=self.cfg["news"]["enabled"])
        ttk.Checkbutton(
            settings_win,
            text="Enabled",
            variable=self.news_enabled,
        ).pack(anchor=tk.W, padx=40)

        # Market
        ttk.Label(settings_win, text="Market Updates:").pack(
            anchor=tk.W, padx=20, pady=(10, 0)
        )
        self.market_enabled = tk.BooleanVar(value=self.cfg["market"]["enabled"])
        ttk.Checkbutton(
            settings_win,
            text="Enabled",
            variable=self.market_enabled,
        ).pack(anchor=tk.W, padx=40)

        # Save button
        def save_settings():
            self.cfg.data["commentary"]["enabled"] = self.commentary_enabled.get()
            self.cfg.data["news"]["enabled"] = self.news_enabled.get()
            self.cfg.data["market"]["enabled"] = self.market_enabled.get()
            settings_win.destroy()

        ttk.Button(settings_win, text="Save", command=save_settings).pack(pady=20)

    def _on_close(self):
        """Minimize to tray instead of closing."""
        self.root.withdraw()

    def _on_tray_show(self, icon, item):
        """Show window from tray."""
        self.root.deiconify()
        self.root.lift()

    def _on_tray_exit(self, icon, item):
        """Exit the application."""
        self.controller.stop()
        icon.stop()
        self.root.quit()


def main():
    root = tk.Tk()
    app = AIdjGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
