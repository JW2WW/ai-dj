"""DJ profile manager UI: add, edit, delete, and customize DJ personas."""
import logging
import logging
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageDraw, ImageTk

from dj_profile import DJManager, DJProfile, AVAILABLE_VOICES
from news_fetcher import AVAILABLE_SOURCES
from paths import DB_PATH, DJ_IMAGES_DIR, resolve_dj_image

# Voice descriptions for UI
VOICE_DESCRIPTIONS = {
    "en-US-AriaNeural": "Aria (Female, neutral)",
    "en-US-JennyNeural": "Jenny (Female, natural)",
    "en-US-AnaNeural": "Ana (Female, child)",
    "en-US-AvaNeural": "Ava (Female, bright)",
    "en-US-EmmaNeural": "Emma (Female, soft)",
    "en-US-MichelleNeural": "Michelle (Female, warm)",
    "en-US-GuyNeural": "Guy (Male, neutral)",
    "en-US-BrianNeural": "Brian (Male, friendly)",
    "en-US-ChristopherNeural": "Christopher (Male, calm)",
    "en-US-RogerNeural": "Roger (Male, deep)",
    "en-US-EricNeural": "Eric (Male, young)",
    "en-US-AndrewNeural": "Andrew (Male, casual)",
}


class DJManagerWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("DJ Manager")
        self.root.geometry("900x600")

        self.manager = DJManager(DB_PATH, DJ_IMAGES_DIR)
        self.current_dj = None
        self.djs = []

        self._setup_ui()
        self.root.after(100, self._refresh_dj_list)  # Refresh after UI is ready

    def _setup_ui(self):
        """Build the DJ manager UI."""
        # Top section: Add DJ button
        top_frame = ttk.Frame(self.root)
        top_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(top_frame, text="Manage DJ Profiles", font=("Arial", 14, "bold")).pack(side=tk.LEFT)
        ttk.Button(top_frame, text="+ Add New DJ", command=self._on_add_dj).pack(side=tk.RIGHT)

        # Main content: DJ list on left, details on right
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Left side: DJ list
        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        ttk.Label(left_frame, text="DJs", font=("Arial", 10, "bold")).pack(anchor=tk.W)

        # Listbox for DJs
        self.dj_listbox = tk.Listbox(left_frame, height=20)
        self.dj_listbox.pack(fill=tk.BOTH, expand=True)
        self.dj_listbox.bind('<<ListboxSelect>>', self._on_dj_select)

        # Right side: DJ details
        right_frame = ttk.LabelFrame(main_frame, text="DJ Details", padding=10)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # DJ avatar (tk.Label — ttk.Label doesn't support width/height in pixels or bg)
        self.avatar_label = tk.Label(right_frame, bg="gray", width=15, height=6)
        self.avatar_label.pack(pady=10)

        ttk.Button(right_frame, text="Upload Image", command=self._on_upload_image).pack(pady=5)

        # DJ details form
        details_frame = ttk.Frame(right_frame)
        details_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        ttk.Label(details_frame, text="Stage Name:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.stage_name_var = tk.StringVar()
        ttk.Entry(details_frame, textvariable=self.stage_name_var, width=30).grid(row=0, column=1)

        ttk.Label(details_frame, text="Station:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.station_var = tk.StringVar()
        ttk.Entry(details_frame, textvariable=self.station_var, width=30).grid(row=1, column=1)

        ttk.Label(details_frame, text="Genre:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.genre_var = tk.StringVar()
        ttk.Entry(details_frame, textvariable=self.genre_var, width=30).grid(row=2, column=1)

        ttk.Label(details_frame, text="Voice:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.voice_var = tk.StringVar()
        voice_combo = ttk.Combobox(details_frame, textvariable=self.voice_var, width=27, state="readonly")
        voice_combo["values"] = [VOICE_DESCRIPTIONS.get(v, v) for v in AVAILABLE_VOICES]
        voice_combo.grid(row=3, column=1)

        ttk.Label(details_frame, text="Tone:").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.tone_var = tk.StringVar()
        tone_combo = ttk.Combobox(details_frame, textvariable=self.tone_var, width=27, state="readonly")
        tone_combo["values"] = ["calm", "smooth", "professional", "energetic", "enthusiastic"]
        tone_combo.grid(row=4, column=1)

        ttk.Label(details_frame, text="Speed:").grid(row=5, column=0, sticky=tk.W, pady=5)
        self.speed_var = tk.StringVar()
        speed_spin = ttk.Spinbox(details_frame, from_=0.5, to=2.0, increment=0.1, textvariable=self.speed_var, width=28)
        speed_spin.grid(row=5, column=1)

        # News reading speed (separate from music-talk speed)
        ttk.Label(details_frame, text="News Speed:").grid(row=6, column=0, sticky=tk.W, pady=5)
        self.news_speed_var = tk.StringVar()
        news_speed_spin = ttk.Spinbox(details_frame, from_=0.5, to=1.5, increment=0.05, textvariable=self.news_speed_var, width=28)
        news_speed_spin.grid(row=6, column=1)

        # News sources — multi-select list (Ctrl/Shift-click to pick several)
        ttk.Label(details_frame, text="News Sources:").grid(row=7, column=0, sticky=tk.NW, pady=5)
        news_src_frame = ttk.Frame(details_frame)
        news_src_frame.grid(row=7, column=1, sticky=tk.EW, pady=5)
        news_scroll = ttk.Scrollbar(news_src_frame, orient=tk.VERTICAL)
        self.news_sources_listbox = tk.Listbox(
            news_src_frame, selectmode=tk.MULTIPLE, height=8,
            exportselection=False, yscrollcommand=news_scroll.set,
        )
        news_scroll.config(command=self.news_sources_listbox.yview)
        news_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.news_sources_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        for source in AVAILABLE_SOURCES:
            self.news_sources_listbox.insert(tk.END, source)

        # Buttons
        button_frame = ttk.Frame(right_frame)
        button_frame.pack(fill=tk.X, pady=10)

        ttk.Button(button_frame, text="Save", command=self._on_save_dj).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Delete", command=self._on_delete_dj).pack(side=tk.LEFT, padx=5)

    def _refresh_dj_list(self):
        """Refresh the DJ listbox."""
        try:
            self.dj_listbox.delete(0, tk.END)
            self.djs = self.manager.list_djs()
            for i, dj in enumerate(self.djs):
                self.dj_listbox.insert(tk.END, dj.stage_name)

            # Select first DJ if available
            if self.djs:
                self.dj_listbox.select_set(0)
                self._on_dj_select(None)
        except Exception as e:
            logging.error(f"[DJ Manager] Error refreshing list: {e}")

    def _on_dj_select(self, event):
        """Handle DJ selection."""
        try:
            selection = self.dj_listbox.curselection()
            if not selection:
                return

            self.current_dj = self.djs[selection[0]]
            self._display_dj(self.current_dj)
        except Exception as e:
            logging.error(f"[DJ Manager] Error selecting DJ: {e}")

    def _display_dj(self, dj: DJProfile):
        """Display DJ details in the form."""
        self.stage_name_var.set(dj.stage_name)
        self.station_var.set(dj.station_name)
        self.genre_var.set(dj.music_genre)

        # Set voice (match by value)
        voice_desc = VOICE_DESCRIPTIONS.get(dj.voice, dj.voice)
        self.voice_var.set(voice_desc)

        self.tone_var.set(dj.tone or "calm")
        self.speed_var.set(str(dj.speed or 1.0))
        self.news_speed_var.set(str(dj.news_speed if dj.news_speed else 1.0))

        # Highlight this DJ's selected news sources in the multi-select list
        self.news_sources_listbox.selection_clear(0, tk.END)
        selected = set()
        if dj.news_sources:
            selected = {s.strip() for s in dj.news_sources.split(",") if s.strip()}
        for i, source in enumerate(AVAILABLE_SOURCES):
            if source in selected:
                self.news_sources_listbox.selection_set(i)

        # Display avatar
        self._display_avatar(dj)

    def _display_avatar(self, dj: DJProfile):
        """Display DJ's image or placeholder."""
        if dj.image_path:
            image_file = resolve_dj_image(dj.image_path)
            if image_file and image_file.exists():
                try:
                    img = Image.open(image_file)
                    img.thumbnail((200, 200), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    self.avatar_label.image = photo
                    # Reset width/height: once an image is set they are pixel units,
                    # and the label's original 15x6 char size would clip the image.
                    self.avatar_label.config(image=photo, width=img.width, height=img.height)
                    return
                except Exception as e:
                    logging.error(f"[DJ Manager] Failed to display avatar: {e}")

        # Placeholder with initials
        img = Image.new("RGB", (200, 200), color="gray")
        draw = ImageDraw.Draw(img)
        initials = "".join(word[0].upper() for word in dj.stage_name.split())
        draw.text((100, 100), initials, fill="white")
        photo = ImageTk.PhotoImage(img)
        self.avatar_label.image = photo
        self.avatar_label.config(image=photo, width=200, height=200)

    def _on_upload_image(self):
        """Upload an image for the current DJ."""
        if not self.current_dj:
            messagebox.showwarning("No DJ Selected", "Please select a DJ first")
            return

        file_path = filedialog.askopenfilename(
            title="Select DJ Image",
            filetypes=[("Image Files", "*.jpg *.png *.jpeg"), ("All Files", "*.*")],
        )

        if file_path:
            try:
                # Copy image to DJ images directory
                img_name = f"{self.current_dj.id}.jpg"
                dest_path = DJ_IMAGES_DIR / img_name
                DJ_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

                # Convert and save as JPEG. JPEG can't hold an alpha channel, so
                # flatten RGBA/LA/P images onto a white background first.
                img = Image.open(file_path)
                if img.mode in ("RGBA", "LA", "P"):
                    img = img.convert("RGBA")
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[-1])
                    img = background
                elif img.mode != "RGB":
                    img = img.convert("RGB")
                img.save(dest_path, "JPEG")

                # Update DJ profile — store only filename, not full path
                # (so images work on other computers too)
                self.current_dj.image_path = img_name
                self.manager.create_dj(self.current_dj)
                self._display_avatar(self.current_dj)
                messagebox.showinfo("Success", "Image uploaded successfully")
            except Exception as e:
                logging.error(f"[DJ Manager] Failed to upload image: {e}")

    def _on_save_dj(self):
        """Save DJ profile changes."""
        if not self.current_dj:
            messagebox.showwarning("No DJ Selected", "Please select a DJ first")
            return

        # Get voice value (reverse lookup from description)
        voice_desc = self.voice_var.get()
        voice = None
        for v, desc in VOICE_DESCRIPTIONS.items():
            if desc == voice_desc:
                voice = v
                break

        if not voice:
            messagebox.showerror("Invalid Voice", "Please select a valid voice")
            return

        # Collect selected news sources from the multi-select list
        selected_sources = [
            AVAILABLE_SOURCES[i] for i in self.news_sources_listbox.curselection()
        ]
        news_sources = ",".join(selected_sources) if selected_sources else None

        # Update DJ
        self.current_dj.stage_name = self.stage_name_var.get()
        self.current_dj.station_name = self.station_var.get()
        self.current_dj.music_genre = self.genre_var.get()
        self.current_dj.voice = voice
        self.current_dj.tone = self.tone_var.get()
        self.current_dj.speed = float(self.speed_var.get())
        self.current_dj.news_speed = float(self.news_speed_var.get())
        self.current_dj.news_sources = news_sources

        try:
            self.manager.create_dj(self.current_dj)
            self._refresh_dj_list()
            messagebox.showinfo("Success", f"DJ '{self.current_dj.stage_name}' updated")
        except Exception as e:
            logging.error(f"[DJ Manager] Failed to save DJ: {e}")

    def _on_delete_dj(self):
        """Delete the current DJ."""
        if not self.current_dj:
            messagebox.showwarning("No DJ Selected", "Please select a DJ first")
            return

        if messagebox.askyesno("Confirm Delete", f"Delete '{self.current_dj.stage_name}'?"):
            try:
                self.manager.delete_dj(self.current_dj.id)
                self._refresh_dj_list()
                self.current_dj = None
                self.stage_name_var.set("")
                self.station_var.set("")
                self.genre_var.set("")
                messagebox.showinfo("Success", "DJ deleted")
            except Exception as e:
                logging.error(f"[DJ Manager] Failed to delete DJ: {e}")

    def _on_add_dj(self):
        """Open dialog to create a new DJ."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Create New DJ")
        dialog.geometry("500x400")
        dialog.resizable(False, False)

        # Keep reference to dialog to prevent garbage collection
        dialog.attributes('-topmost', True)

        title_label = tk.Label(dialog, text="New DJ Profile", font=("Arial", 14, "bold"))
        title_label.pack(pady=15, padx=20)

        form_frame = tk.Frame(dialog)
        form_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        # Stage Name
        tk.Label(form_frame, text="Stage Name:").grid(row=0, column=0, sticky=tk.W, pady=8)
        stage_entry = tk.Entry(form_frame, width=40)
        stage_entry.grid(row=0, column=1, sticky=tk.EW, padx=10)
        stage_entry.focus()

        # Station
        tk.Label(form_frame, text="Station:").grid(row=1, column=0, sticky=tk.W, pady=8)
        station_entry = tk.Entry(form_frame, width=40)
        station_entry.grid(row=1, column=1, sticky=tk.EW, padx=10)

        # Genre
        tk.Label(form_frame, text="Genre:").grid(row=2, column=0, sticky=tk.W, pady=8)
        genre_entry = tk.Entry(form_frame, width=40)
        genre_entry.grid(row=2, column=1, sticky=tk.EW, padx=10)

        # Voice
        tk.Label(form_frame, text="Voice:").grid(row=3, column=0, sticky=tk.W, pady=8)
        voice_var = tk.StringVar(value="Brian (Male, friendly)")
        voice_values = [VOICE_DESCRIPTIONS.get(v, v) for v in AVAILABLE_VOICES]
        voice_combo = ttk.Combobox(form_frame, textvariable=voice_var, values=voice_values, width=37, state="readonly")
        voice_combo.grid(row=3, column=1, sticky=tk.EW, padx=10)

        # Tone
        tk.Label(form_frame, text="Tone:").grid(row=4, column=0, sticky=tk.W, pady=8)
        tone_var = tk.StringVar(value="enthusiastic")
        tone_combo = ttk.Combobox(form_frame, textvariable=tone_var, values=["calm", "smooth", "professional", "energetic", "enthusiastic"], width=37, state="readonly")
        tone_combo.grid(row=4, column=1, sticky=tk.EW, padx=10)

        # Speed
        tk.Label(form_frame, text="Speed:").grid(row=5, column=0, sticky=tk.W, pady=8)
        speed_var = tk.StringVar(value="1.0")
        speed_spin = ttk.Spinbox(form_frame, from_=0.5, to=2.0, increment=0.1, textvariable=speed_var, width=38)
        speed_spin.grid(row=5, column=1, sticky=tk.EW, padx=10)

        form_frame.columnconfigure(1, weight=1)

        # Buttons
        button_frame = tk.Frame(dialog)
        button_frame.pack(fill=tk.X, padx=20, pady=15)

        def on_create():
            # Get values directly from Entry widgets (not StringVar)
            stage_name = stage_entry.get().strip()
            station = station_entry.get().strip()
            genre = genre_entry.get().strip()

            # Debug output
            print(f"Stage: '{stage_name}' (len={len(stage_name)})")
            print(f"Station: '{station}' (len={len(station)})")
            print(f"Genre: '{genre}' (len={len(genre)})")

            if not stage_name or not station or not genre:
                messagebox.showwarning("Missing Fields", f"Please fill in all fields.\nStage: {len(stage_name)} chars\nStation: {len(station)} chars\nGenre: {len(genre)} chars")
                return

            try:
                # Get voice value (reverse lookup from description)
                voice_desc = voice_var.get()
                voice = None
                for v, desc in VOICE_DESCRIPTIONS.items():
                    if desc == voice_desc:
                        voice = v
                        break

                if not voice:
                    voice = "en-US-BrianNeural"

                # Create new DJ
                dj_id = stage_name.lower().replace(" ", "_").replace("-", "_")
                new_dj = DJProfile(
                    id=dj_id,
                    stage_name=stage_name,
                    station_name=station,
                    gender="male",
                    sexual_orientation="straight",
                    music_genre=genre,
                    generation="millennial",
                    voice=voice,
                    tone=tone_var.get(),
                    speed=float(speed_var.get()),
                )

                print(f"[DJ Manager] Creating DJ: {dj_id}")
                self.manager.create_dj(new_dj)
                print(f"[DJ Manager] DJ created, refreshing list...")
                dialog.destroy()
                self._refresh_dj_list()
                messagebox.showinfo("Success", f"DJ '{stage_name}' created successfully!")
            except Exception as e:
                logging.error(f"Error creating DJ: {e}")

        ttk.Button(button_frame, text="Create DJ", command=on_create).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)


def launch_dj_manager(parent=None):
    """Launch the DJ manager window.

    If parent is provided (main app is running), use a Toplevel window.
    Otherwise create a standalone Tk root (for running this file directly).
    """
    if parent is not None:
        # Main app already has a Tk() root running — use Toplevel to avoid
        # the "two Tk instances" bug that leaves widgets blank.
        win = tk.Toplevel(parent)
        DJManagerWindow(win)
        win.transient(parent)
        win.grab_set()
    else:
        root = tk.Tk()
        DJManagerWindow(root)
        root.mainloop()


if __name__ == "__main__":
    launch_dj_manager()
