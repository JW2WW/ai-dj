"""AI DJ App: Main entry point with music directory selector, DJ selector, and enhanced GUI."""
import tkinter as tk

from dj_selector import select_dj
from gui_enhanced import EnhancedAIdjGUI
from music_directory import select_music_directory
from paths import DB_PATH, TTS_CACHE_DIR


def main():
    """Launch DJ selector, then music directory selector, then enhanced main GUI."""
    # Show DJ selector first
    print("Launching DJ Selector...")
    selected_dj = select_dj()

    if not selected_dj:
        print("No DJ selected. Exiting.")
        return

    print(f"Selected: {selected_dj.stage_name} at {selected_dj.station_name}")

    # Force music directory selection after choosing a DJ
    print("Prompting for music directory...")
    music_dir = select_music_directory()

    if not music_dir:
        print("No music directory selected. Exiting.")
        return

    print(f"Using music directory: {music_dir}")

    # Launch enhanced GUI with selected DJ and music directory
    root = tk.Tk()
    app = EnhancedAIdjGUI(root, dj=selected_dj, music_dir=music_dir)
    root.mainloop()


if __name__ == "__main__":
    main()
