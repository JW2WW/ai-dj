"""DJ selector: initial screen for choosing which DJ to be for this session."""
import logging
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

from dj_profile import DJManager
from paths import DB_PATH, DJ_IMAGES_DIR, resolve_dj_image

# Default DJ images (placeholder colors if no image exists)
DJ_COLORS = {
    "morning_mike": "#4A90E2",
    "night_nina": "#E24A90",
    "sunny_sam": "#90E24A",
    "late_night_leo": "#7B68EE",
}


class DJSelectorWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("AI DJ — Choose Your DJ")
        self.root.geometry("1000x600")
        self.root.resizable(True, True)

        self.manager = DJManager(DB_PATH, DJ_IMAGES_DIR)
        self.selected_dj = None
        self._photo_refs = []  # Keep PhotoImage references alive

        # Setup UI
        self._setup_ui()

    def _setup_ui(self):
        """Build the DJ selector screen."""
        # Title
        title = ttk.Label(
            self.root,
            text="Select Your DJ Persona",
            font=("Arial", 20, "bold"),
        )
        title.pack(pady=20)

        # DJ cards frame — uses a grid that wraps to multiple rows
        cards_frame = ttk.Frame(self.root)
        cards_frame.pack(pady=10, padx=20, fill=tk.BOTH, expand=True)

        djs = self.manager.list_djs()

        # Choose column count: up to 4 per row, but no more than the DJ count
        max_cols = min(4, len(djs)) if djs else 1
        rows = (len(djs) + max_cols - 1) // max_cols  # ceil division

        # Give every column/row equal weight so cards space evenly with
        # consistent margins regardless of how many DJs there are.
        for c in range(max_cols):
            cards_frame.columnconfigure(c, weight=1, uniform="dj")
        for r in range(rows):
            cards_frame.rowconfigure(r, weight=1, uniform="dj")

        for i, dj in enumerate(djs):
            row, col = divmod(i, max_cols)
            self._create_dj_card(cards_frame, dj, row, col)

        # Resize window to fit the grid nicely
        win_w = min(1200, max_cols * 280 + 60)
        win_h = min(900, rows * 420 + 140)
        self.root.geometry(f"{win_w}x{win_h}")

        # Instructions
        instructions = ttk.Label(
            self.root,
            text="Click a card to select your DJ. Each has their own style, voice, and personality.",
            font=("Arial", 9),
            foreground="gray",
        )
        instructions.pack(pady=10)

    def _create_dj_card(self, parent, dj, row, col):
        """Create a clickable DJ card with image, name, and station."""
        # Card frame — placed in the grid with uniform padding on all sides
        card = tk.Frame(
            parent,
            bg=DJ_COLORS.get(dj.id, "#CCCCCC"),
            relief=tk.RAISED,
            bd=2,
            highlightthickness=2,
            highlightcolor="#333333",
        )
        card.grid(row=row, column=col, padx=15, pady=15, ipadx=10, ipady=10, sticky="n")

        # DJ image if uploaded, otherwise initial letter as placeholder
        photo = None
        if dj.image_path:
            image_file = resolve_dj_image(dj.image_path)
            if image_file and image_file.exists():
                try:
                    img = Image.open(image_file)
                    # Preserve full image (no cropping); scale to a consistent box
                    # so every card is the same width regardless of source size.
                    img.thumbnail((220, 260), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    self._photo_refs.append(photo)  # Prevent garbage collection
                except Exception as e:
                    logging.error(f"Failed to load DJ image {dj.image_path}: {e}")
            else:
                photo = None
        else:
            photo = None

        if photo:
            image_label = tk.Label(
                card,
                bg=DJ_COLORS.get(dj.id, "#CCCCCC"),
                image=photo,
                width=photo.width(),
                height=photo.height(),
            )
        else:
            image_label = tk.Label(
                card,
                bg=DJ_COLORS.get(dj.id, "#CCCCCC"),
                fg="white",
                font=("Arial", 48, "bold"),
                text=dj.stage_name[0],  # First letter as avatar
                width=8,
                height=4,
            )
        image_label.pack()

        # DJ name
        name_label = tk.Label(
            card,
            text=dj.stage_name,
            bg=DJ_COLORS.get(dj.id, "#CCCCCC"),
            fg="white",
            font=("Arial", 14, "bold"),
        )
        name_label.pack()

        # Station name
        station_label = tk.Label(
            card,
            text=dj.station_name,
            bg=DJ_COLORS.get(dj.id, "#CCCCCC"),
            fg="white",
            font=("Arial", 10),
        )
        station_label.pack()

        # Genre
        genre_label = tk.Label(
            card,
            text=dj.music_genre,
            bg=DJ_COLORS.get(dj.id, "#CCCCCC"),
            fg="white",
            font=("Arial", 9, "italic"),
        )
        genre_label.pack()

        # Click handler
        def on_click(event):
            self.selected_dj = dj
            self.root.quit()

        for widget in [card, image_label, name_label, station_label, genre_label]:
            widget.bind("<Button-1>", on_click)
            # Highlight on hover
            widget.bind(
                "<Enter>",
                lambda e, c=card: c.config(relief=tk.SUNKEN, bd=3),
            )
            widget.bind(
                "<Leave>",
                lambda e, c=card: c.config(relief=tk.RAISED, bd=2),
            )


def select_dj() -> "DJProfile | None":
    """Show DJ selector and return the selected DJ, or None if cancelled."""
    root = tk.Tk()
    selector = DJSelectorWindow(root)
    root.mainloop()
    root.destroy()
    return selector.selected_dj


if __name__ == "__main__":
    dj = select_dj()
    if dj:
        print(f"Selected: {dj.stage_name} at {dj.station_name}")
        print(f"  Voice: {dj.voice}, Tone: {dj.tone}, Speed: {dj.speed}")
    else:
        print("No DJ selected (window closed)")
