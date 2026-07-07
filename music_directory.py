"""Music directory selector: let user choose their music folder at startup."""
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from config import get_config


def get_music_directory() -> Path | None:
    """Show directory selector if not configured, otherwise return configured path."""
    cfg = get_config()
    music_dir_str = cfg.get("playback", "music_directory")

    # If configured and exists, use it
    if music_dir_str:
        music_dir = Path(music_dir_str)
        if music_dir.exists() and music_dir.is_dir():
            return music_dir

    # Otherwise ask user
    return select_music_directory()


def select_music_directory() -> Path | None:
    """Show a dialog for user to select their music directory."""
    root = tk.Tk()
    root.withdraw()  # Hide root window
    root.title("AI DJ — Select Music Directory")

    # Show directory selection dialog
    folder = filedialog.askdirectory(
        title="Select your music folder (containing .mp3 files)",
        initialdir=str(Path.home() / "Music"),
    )

    root.destroy()

    if not folder:
        return None

    music_dir = Path(folder)

    # Validate: must have MP3s (recursive search)
    mp3_files = list(music_dir.glob("**/*.mp3"))
    if not mp3_files:
        messagebox.showwarning(
            "No MP3 Files",
            f"No MP3 files found in {folder}.\n\nPlease select a folder with MP3 files.",
        )
        return select_music_directory()

    # Save to config
    cfg = get_config()
    cfg.data["playback"]["music_directory"] = str(music_dir)
    cfg.save()

    return music_dir


def settings_dialog() -> Path | None:
    """Show a settings window to change music directory."""
    root = tk.Tk()
    root.title("AI DJ Settings")
    root.geometry("500x250")

    cfg = get_config()
    music_dir_str = cfg.get("playback", "music_directory", "")

    # Current directory display
    ttk.Label(root, text="Music Directory:", font=("Arial", 10, "bold")).pack(
        pady=10, padx=10, anchor=tk.W
    )

    dir_frame = ttk.Frame(root)
    dir_frame.pack(pady=5, padx=10, fill=tk.BOTH, expand=True)

    dir_label = ttk.Label(
        dir_frame,
        text=music_dir_str or "(not set)",
        font=("Arial", 9),
        foreground="blue" if music_dir_str else "gray",
        wraplength=400,
    )
    dir_label.pack(anchor=tk.W)

    # Browse button
    def on_browse():
        new_dir = select_music_directory()
        if new_dir:
            dir_label.config(text=str(new_dir), foreground="blue")

    ttk.Button(dir_frame, text="Browse...", command=on_browse).pack(anchor=tk.W, pady=5)

    # Info
    info = ttk.Label(
        root,
        text="The app will scan this directory for MP3 files each time it starts.",
        font=("Arial", 9),
        foreground="gray",
    )
    info.pack(pady=20, padx=10)

    # OK button
    def on_ok():
        root.destroy()

    ttk.Button(root, text="OK", command=on_ok).pack(pady=10)

    root.mainloop()
    return None
