"""Enhanced GUI: Playlist view, search, history, inline toggles, keyboard shortcuts, music blending, DJ voices."""
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from PIL import Image, ImageDraw, ImageTk
import pystray
from io import BytesIO

from config import get_config
from dj_profile import DJProfile
from music_directory import select_music_directory
from playback_controller import PlaybackController
from queue_manager import QueueManager
from artist_images import get_artist_image
from dj_manager_ui import launch_dj_manager
from paths import DB_PATH, TTS_CACHE_DIR, DJ_IMAGES_DIR


def create_icon():
    """Create a simple tray icon (AI DJ in blue)."""
    size = 64
    img = Image.new("RGB", (size, size), color="white")
    draw = ImageDraw.Draw(img)
    draw.ellipse([10, 40, 25, 55], fill="blue")
    draw.line([20, 40, 20, 10], fill="blue", width=3)
    draw.ellipse([30, 30, 45, 45], fill="blue")
    draw.line([37, 30, 37, 5], fill="blue", width=3)
    return img


class EnhancedAIdjGUI:
    def __init__(self, root, dj: DJProfile | None = None, music_dir: Path | None = None):
        self.root = root
        self.dj = dj
        self.music_dir = music_dir or Path(r"C:\Users\AI\Desktop\mp3s")
        self.root.title(f"AI DJ — {dj.stage_name}" if dj else "AI DJ")
        self.root.geometry("1200x800")
        self.root.resizable(True, True)

        self.cfg = get_config()
        # Create queue_manager in GUI thread (not playback thread) to avoid SQLite threading issues
        self.queue_manager = QueueManager(DB_PATH, self.music_dir)
        self.queue_manager.sync_library()
        self.controller = PlaybackController(self.music_dir, DB_PATH, TTS_CACHE_DIR, dj=dj, queue_manager=self.queue_manager)
        self.controller.on_track_changed = self._on_track_changed

        # Track list for search
        self.all_tracks = self.queue_manager.queue_manager.conn.execute(
            "SELECT * FROM tracks ORDER BY artist, title"
        ).fetchall() if hasattr(self.queue_manager, 'queue_manager') else []

        # Setup UI
        self._setup_ui()

        # Start playback in background
        self.controller.start()

        # Set volume slider after controller starts
        self.volume_slider.set(self.cfg["playback"]["volume"])

        # Bind keyboard shortcuts
        self._setup_keyboard()

        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Setup system tray
        self._setup_tray()

    def _setup_ui(self):
        """Build the enhanced main window UI."""
        # Top section: DJ image on left, album art on right
        images_frame = tk.Frame(self.root)
        images_frame.pack(fill=tk.BOTH, expand=False, padx=10, pady=10)

        # DJ image on the left
        self.dj_image_label = tk.Label(images_frame, bg="gray")
        self.dj_image_label.pack(side=tk.LEFT, padx=(0, 10))

        # Album art on the right
        self.album_art_label = tk.Label(images_frame, bg="gray")
        self.album_art_label.pack(side=tk.LEFT)

        # DJ info and now playing (below images)
        top_frame = ttk.Frame(self.root)
        top_frame.pack(fill=tk.X, padx=10, pady=10)

        if self.dj:
            dj_info = ttk.Label(
                top_frame,
                text=f"{self.dj.stage_name} — {self.dj.station_name}",
                font=("Arial", 12, "bold"),
                foreground="blue",
            )
            dj_info.pack(anchor=tk.W)
            genre_info = ttk.Label(
                top_frame,
                text=f"{self.dj.music_genre.title()} • {self.dj.generation.replace('_', ' ').title()}",
                font=("Arial", 9),
                foreground="gray",
            )
            genre_info.pack(anchor=tk.W)

        # Now Playing section
        now_label = ttk.Label(top_frame, text="Now Playing:", font=("Arial", 10, "bold"))
        now_label.pack(anchor=tk.W, pady=(10, 2))

        now_playing_frame = ttk.Frame(top_frame)
        now_playing_frame.pack(anchor=tk.W, fill=tk.X)

        self.now_playing = ttk.Label(
            now_playing_frame,
            text="Loading...",
            font=("Arial", 11),
            foreground="blue",
        )
        self.now_playing.pack(side=tk.LEFT)

        self.thumbs_down_btn = tk.Button(
            now_playing_frame, text="👎", width=3, command=self._on_thumbs_down,
            relief=tk.RAISED, bd=2
        )
        self.thumbs_down_btn.pack(side=tk.LEFT, padx=5)

        self.thumbs_up_btn = tk.Button(
            now_playing_frame, text="👍", width=3, command=self._on_thumbs_up,
            relief=tk.RAISED, bd=2
        )
        self.thumbs_up_btn.pack(side=tk.LEFT)

        self.up_next = ttk.Label(
            top_frame,
            text="Up next: ...",
            font=("Arial", 9),
            foreground="gray",
        )
        self.up_next.pack(anchor=tk.W, pady=(2, 0))

        # Store current track for rating
        self.current_track_id = None
        self.current_track = None

        # Playback controls
        controls_frame = ttk.Frame(self.root)
        controls_frame.pack(fill=tk.X, padx=10, pady=10)

        self.play_btn = ttk.Button(
            controls_frame, text="⏸ Pause", command=self._on_pause_click
        )
        self.play_btn.pack(side=tk.LEFT, padx=5)

        ttk.Button(controls_frame, text="⏭ Skip", command=self._on_skip_click).pack(
            side=tk.LEFT, padx=5
        )

        ttk.Button(controls_frame, text="📁 Change Directory", command=self._on_change_directory_click).pack(
            side=tk.LEFT, padx=5
        )

        ttk.Button(controls_frame, text="🎤 DJs", command=self._on_dj_manager_click).pack(
            side=tk.LEFT, padx=5
        )

        # Volume control
        vol_frame = ttk.Frame(controls_frame)
        vol_frame.pack(side=tk.LEFT, padx=20)

        ttk.Label(vol_frame, text="Volume:").pack(side=tk.LEFT)
        self.volume_label = ttk.Label(vol_frame, text="80%")
        self.volume_slider = ttk.Scale(
            vol_frame,
            from_=0,
            to=100,
            orient=tk.HORIZONTAL,
            command=self._on_volume_change,
        )
        self.volume_slider.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)
        self.volume_label.pack(side=tk.LEFT)

        # Inline toggles for content
        toggles_frame = ttk.Frame(controls_frame)
        toggles_frame.pack(side=tk.RIGHT, padx=10)

        self.commentary_var = tk.BooleanVar(value=self.cfg["commentary"]["enabled"])
        ttk.Checkbutton(
            toggles_frame,
            text="Commentary",
            variable=self.commentary_var,
            command=self._on_commentary_toggle,
        ).pack(side=tk.LEFT, padx=5)

        self.news_var = tk.BooleanVar(value=self.cfg["news"]["enabled"])
        ttk.Checkbutton(
            toggles_frame,
            text="News",
            variable=self.news_var,
            command=self._on_news_toggle,
        ).pack(side=tk.LEFT, padx=5)

        self.news_every_song_var = tk.BooleanVar(
            value=self.cfg["news"].get("after_every_song", False)
        )
        ttk.Checkbutton(
            toggles_frame,
            text="News/song",
            variable=self.news_every_song_var,
            command=self._on_news_every_song_toggle,
        ).pack(side=tk.LEFT, padx=5)

        self.market_var = tk.BooleanVar(value=self.cfg["market"]["enabled"])
        ttk.Checkbutton(
            toggles_frame,
            text="Market",
            variable=self.market_var,
            command=self._on_market_toggle,
        ).pack(side=tk.LEFT, padx=5)

        # Search bar
        search_frame = ttk.Frame(self.root)
        search_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, padx=(0, 5))
        self.search_var = tk.StringVar()
        self.search_var.trace("w", self._on_search_change)
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=40)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Notebook (tabs) for Playlist and History
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Playlist tab
        playlist_frame = ttk.Frame(notebook)
        notebook.add(playlist_frame, text="Playlist")
        self._setup_playlist_tab(playlist_frame)

        # History tab
        history_frame = ttk.Frame(notebook)
        notebook.add(history_frame, text="Recently Played")
        self._setup_history_tab(history_frame)

        # Status bar
        self.status = ttk.Label(
            self.root,
            text="Ready. Spacebar to play/pause, arrow keys to control.",
            font=("Arial", 8),
            foreground="gray",
        )
        self.status.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=5)

    def _setup_playlist_tab(self, parent):
        """Setup the playlist view tab with scrollbars."""
        # Frame to hold treeview and scrollbars
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        # Scrollbars
        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        hsb = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL)

        # Treeview for upcoming tracks
        columns = ("artist", "title", "duration")
        self.playlist_tree = ttk.Treeview(
            tree_frame, columns=columns, show="tree headings", height=20,
            yscrollcommand=vsb.set, xscrollcommand=hsb.set
        )

        # Configure scrollbars
        vsb.config(command=self.playlist_tree.yview)
        hsb.config(command=self.playlist_tree.xview)

        self.playlist_tree.column("#0", width=0, stretch=tk.NO)
        self.playlist_tree.column("artist", anchor=tk.W, width=250)
        self.playlist_tree.column("title", anchor=tk.W, width=450)
        self.playlist_tree.column("duration", anchor=tk.CENTER, width=80)

        self.playlist_tree.heading("#0", text="", anchor=tk.W)
        self.playlist_tree.heading("artist", text="Artist", anchor=tk.W)
        self.playlist_tree.heading("title", text="Title", anchor=tk.W)
        self.playlist_tree.heading("duration", text="Duration", anchor=tk.CENTER)

        # Grid layout for treeview and scrollbars
        self.playlist_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        # Right-click context menu
        self.playlist_tree.bind("<Button-3>", self._on_playlist_rightclick)

        # Populate with upcoming tracks
        self._refresh_playlist()

    def _setup_history_tab(self, parent):
        """Setup the recently played history tab with scrollbars."""
        # Frame to hold treeview and scrollbars
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        # Scrollbars
        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        hsb = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL)

        # Treeview for history
        columns = ("artist", "title", "played_at")
        self.history_tree = ttk.Treeview(
            tree_frame, columns=columns, show="tree headings", height=20,
            yscrollcommand=vsb.set, xscrollcommand=hsb.set
        )

        # Configure scrollbars
        vsb.config(command=self.history_tree.yview)
        hsb.config(command=self.history_tree.xview)

        self.history_tree.column("#0", width=0, stretch=tk.NO)
        self.history_tree.column("artist", anchor=tk.W, width=250)
        self.history_tree.column("title", anchor=tk.W, width=450)
        self.history_tree.column("played_at", anchor=tk.CENTER, width=80)

        self.history_tree.heading("#0", text="", anchor=tk.W)
        self.history_tree.heading("artist", text="Artist", anchor=tk.W)
        self.history_tree.heading("title", text="Title", anchor=tk.W)
        self.history_tree.heading("played_at", text="Time", anchor=tk.CENTER)

        # Grid layout for treeview and scrollbars
        self.history_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        # Right-click context menu
        self.history_tree.bind("<Button-3>", self._on_history_rightclick)

        # Populate with history
        self._refresh_history()

    def _refresh_playlist(self):
        """Refresh the playlist view with upcoming tracks."""
        for item in self.playlist_tree.get_children():
            self.playlist_tree.delete(item)

        upcoming = self.controller.peek_queue(20)
        for track in upcoming:
            duration = f"{int(track.duration // 60)}:{int(track.duration % 60):02d}" if track.duration else "0:00"
            self.playlist_tree.insert(
                "", "end", values=(track.artist, track.title, duration)
            )

    def _refresh_history(self):
        """Refresh the history view with recently played tracks."""
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)

        history = self.controller.recently_played(20)
        for track in history:
            self.history_tree.insert("", "end", values=(track.artist, track.title, "just now"))

    def _setup_keyboard(self):
        """Setup keyboard shortcuts."""
        self.root.bind("<space>", self._on_space_key)
        self.root.bind("<Right>", self._on_right_key)
        self.root.bind("<Left>", self._on_left_key)

    def _on_space_key(self, event):
        """Spacebar to play/pause."""
        self._on_pause_click()

    def _on_right_key(self, event):
        """Right arrow to skip."""
        self._on_skip_click()

    def _on_left_key(self, event):
        """Left arrow to lower volume."""
        vol = int(self.volume_slider.get())
        self.volume_slider.set(max(0, vol - 5))

    def _on_track_changed(self, track, up_next):
        """Called by controller when track changes."""
        self.root.after(0, lambda: self._update_track_display(track, up_next))

    def _update_track_display(self, track, up_next):
        """Update now playing and refresh playlists."""
        self.now_playing.config(text=f"{track.artist} - {track.title}")
        self.current_track_id = track.id
        self.current_track = track
        if up_next:
            self.up_next.config(text=f"Up next: {up_next.artist} - {up_next.title}")
        self._refresh_playlist()
        self._refresh_history()
        # Load and display DJ image and album art in background
        threading.Thread(target=self._load_dj_image, daemon=True).start()
        threading.Thread(target=self._load_album_art, args=(track,), daemon=True).start()

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

    def _on_commentary_toggle(self):
        """Toggle commentary on/off."""
        self.cfg.data["commentary"]["enabled"] = self.commentary_var.get()

    def _on_news_toggle(self):
        """Toggle news on/off."""
        self.cfg.data["news"]["enabled"] = self.news_var.get()

    def _on_news_every_song_toggle(self):
        """Toggle 'news after every song' on/off."""
        enabled = self.news_every_song_var.get()
        self.cfg.data["news"]["after_every_song"] = enabled
        # Enabling this only makes sense if news itself is on — turn it on too.
        if enabled and not self.news_var.get():
            self.news_var.set(True)
            self.cfg.data["news"]["enabled"] = True
        self.status.config(
            text="News after every song: ON" if enabled else "News after every song: OFF"
        )

    def _on_market_toggle(self):
        """Toggle market on/off."""
        self.cfg.data["market"]["enabled"] = self.market_var.get()

    def _on_search_change(self, *args):
        """Filter playlist by search term."""
        query = self.search_var.get().lower()
        if query:
            # TODO: Implement search filtering
            pass

    def _load_dj_image(self):
        """Load and display the selected DJ's image (same size as DJ selector)."""
        try:
            if not self.dj or not self.dj.image_path:
                return

            # image_path is stored as filename; reconstruct full path
            image_file = DJ_IMAGES_DIR / self.dj.image_path if not Path(self.dj.image_path).is_absolute() else Path(self.dj.image_path)
            if image_file.exists():
                img = Image.open(image_file)
                # Use same sizing as DJ selector: 220x260 with aspect ratio preserved
                img.thumbnail((220, 260), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                # Schedule UI update on main thread
                self.root.after(0, lambda p=photo: self._display_dj_image(p))
        except Exception as e:
            if self.cfg["logging"]["verbose"]:
                print(f"DJ image loading error: {e}")

    def _display_dj_image(self, photo):
        """Display the DJ image on the label."""
        self.dj_image_label.image = photo  # Keep a reference
        self.dj_image_label.config(image=photo)

    def _load_album_art(self, track):
        """Load album art from track (embedded) or local/Wikipedia (fallback)."""
        try:
            image_bytes = track.album_art
            if not image_bytes:
                # Fallback: try local cover art, then Wikipedia artist image
                cache_dir = Path(__file__).parent / "data" / "artist_images"
                verbose = self.cfg["logging"]["verbose"]
                image_bytes = get_artist_image(track.artist, track.path, cache_dir, verbose)

            if image_bytes:
                # Convert bytes to PIL Image and display
                img = Image.open(BytesIO(image_bytes))
                # Resize to match DJ image size (220x260)
                img.thumbnail((220, 260), Image.Resampling.LANCZOS)
                # Convert PIL image to PhotoImage
                photo = ImageTk.PhotoImage(img)
                # Schedule UI update on main thread
                self.root.after(0, lambda p=photo: self._display_album_art(p))
            elif self.cfg["logging"]["verbose"]:
                print(f"No album art found for {track.artist} - {track.title}")
        except Exception as e:
            if self.cfg["logging"]["verbose"]:
                print(f"Album art loading error: {e}")
                import traceback
                traceback.print_exc()

    def _display_album_art(self, photo):
        """Display the album art on the label."""
        self.album_art_label.image = photo  # Keep a reference
        self.album_art_label.config(image=photo)

    def _on_thumbs_down(self):
        """Rate current track as thumbs down (play less frequently)."""
        if self.current_track_id:
            self.controller.rate_track(self.current_track_id, -1)
            self.thumbs_down_btn.config(relief=tk.SUNKEN)
            self.thumbs_up_btn.config(relief=tk.RAISED)
            self.status.config(text="👎 Marked down")

    def _on_thumbs_up(self):
        """Rate current track as thumbs up (play more frequently)."""
        if self.current_track_id:
            self.controller.rate_track(self.current_track_id, 1)
            self.thumbs_up_btn.config(relief=tk.SUNKEN)
            self.thumbs_down_btn.config(relief=tk.RAISED)
            self.status.config(text="👍 Marked up")

    def _on_playlist_rightclick(self, event):
        """Right-click menu on playlist tree."""
        item = self.playlist_tree.selection()
        if not item:
            return

        # Get track from current position (rough approximation)
        upcoming = self.controller.peek_queue(20)
        if upcoming:
            track = upcoming[self.playlist_tree.index(item[0])]
            menu = tk.Menu(self.root, tearoff=False)
            menu.add_command(
                label="Remove from Queue",
                command=lambda: self._remove_from_queue(track),
            )
            menu.post(event.x_root, event.y_root)

    def _remove_from_queue(self, track):
        """Remove a track from the upcoming queue."""
        self.controller.remove_from_queue(track.id)
        self._refresh_playlist()
        self.status.config(text=f"Removed '{track.title}' from queue")

    def _on_history_rightclick(self, event):
        """Right-click menu on history tree."""
        item = self.history_tree.selection()
        if not item:
            return

        # Get track from history (rough approximation)
        history = self.controller.recently_played(20)
        if history:
            track = history[self.history_tree.index(item[0])]
            menu = tk.Menu(self.root, tearoff=False)
            menu.add_command(
                label="Requeue",
                command=lambda: self._requeue_track(track),
            )
            menu.post(event.x_root, event.y_root)

    def _requeue_track(self, track):
        """Add a track back to the queue."""
        self.controller.requeue_track(track.id)
        self._refresh_playlist()
        self.status.config(text=f"Requeued '{track.title}'")

    def _on_dj_manager_click(self):
        """Open the DJ manager window."""
        launch_dj_manager(parent=self.root)

    def _on_change_directory_click(self):
        """Prompt for a new music directory and reload the library immediately."""
        new_dir = select_music_directory()
        if new_dir:
            self.music_dir = new_dir
            # Reload queue manager with new directory
            self.queue_manager = QueueManager(DB_PATH, self.music_dir)
            self.queue_manager.sync_library()
            self.status.config(text=f"Music directory changed to {new_dir}")
            self._refresh_playlist()
            self._refresh_history()

    def _on_close(self):
        """Minimize to tray instead of closing."""
        self.root.withdraw()

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

        def run_tray():
            icon.run()

        tray_thread = threading.Thread(target=run_tray, daemon=True)
        tray_thread.start()
        self.tray_icon = icon

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
    """Launch the enhanced GUI."""
    root = tk.Tk()
    app = EnhancedAIdjGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
