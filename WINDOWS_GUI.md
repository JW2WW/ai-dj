# AI DJ GUI for Windows

A native Windows GUI application with system tray icon for controlling the AI DJ radio station.

## Features

- **System Tray Icon** — Minimize to tray, close button shows tray menu
- **Playback Controls** — Play/pause/skip buttons
- **Volume Control** — Slider for quick volume adjustment
- **Now Playing Display** — Shows current track and up next
- **Settings Panel** — Toggle commentary, news, market updates
- **Background Playback** — Keeps running even when window is minimized

## Installation

### 1. Setup Python Environment

You already have the venv set up. Ensure you're using it:

```bash
cd C:\Users\AI\Desktop\AI_DJ
venv\Scripts\activate
pip install pystray pillow
```

### 2. Create `.env` with API Keys

```bash
copy .env.example .env
# Edit .env and add GEMINI_API_KEY and/or GROQ_API_KEY
```

### 3. Run the GUI

**Option A — Simple (shows console window):**
```bash
ai-dj-gui.bat
```

**Option B — Clean (no console window):**
Double-click `ai-dj-gui.vbs`

**Option C — Manual:**
```bash
python gui.py
```

## Usage

### Main Window

- **Now Playing** — Shows the current track
- **Up Next** — Shows the next track in the queue
- **Pause/Resume** — Pauses playback (queue doesn't advance)
- **Skip** — Skip to next track
- **Volume Slider** — Adjust volume 0-100%
- **Settings** — Configure commentary, news, market toggles

### System Tray

When you close the main window, it minimizes to the system tray:
- **Show** — Restore the window
- **Pause** — Quick pause/resume from tray
- **Skip** — Skip to next track from tray
- **Exit** — Close the app completely

### Configuration

Changes in the Settings panel apply immediately. To persist them permanently, edit `config.yaml` or use environment variables.

Example environment override:
```bash
set PLAYBACK_VOLUME=70
set COMMENTARY_TARGET_SECONDS=20
python gui.py
```

## Advanced: Run as Windows Service

To run AI DJ as a background service (auto-starts on boot, no window):

### Install pywin32

```bash
pip install pywin32
python -m pywin32_postinstall -install
```

### Install the Service

```bash
python windows_service.py install
```

### Start/Stop the Service

```bash
python windows_service.py start
python windows_service.py stop
```

### View Logs

Open Event Viewer → Windows Logs → Application → Look for "AIdjRadio" entries

### Remove the Service

```bash
python windows_service.py remove
```

## Startup Shortcut

To start the GUI automatically when you log in:

1. Create a shortcut to `ai-dj-gui.vbs`
2. Press `Win+R`, type `shell:startup`
3. Copy the shortcut into the startup folder

Now the GUI will launch automatically each time you log in (minimized to tray).

## Troubleshooting

### "No audio output"
- Ensure VLC is installed: `vlc --version` in cmd
- Check Windows audio settings (right-click speaker icon)
- Verify MP3 files exist in `C:\Users\AI\Desktop\mp3s`

### "Module not found" errors
- Activate venv: `venv\Scripts\activate`
- Run from the project directory: `cd C:\Users\AI\Desktop\AI_DJ`

### Settings don't persist
- Changes in the Settings panel only apply to the current session
- For permanent changes, edit `config.yaml` or set environment variables before launching

### Tray icon doesn't appear
- May be hidden in the system tray. Check "Show hidden icons" in taskbar settings
- Click the icon to bring up the window

## File Locations

- **Config:** `C:\Users\AI\Desktop\AI_DJ\config.yaml` (or use `.env` for overrides)
- **Database:** `C:\Users\AI\Desktop\AI_DJ\data\ai_dj.db` (queue state, cache)
- **TTS Cache:** `C:\Users\AI\Desktop\AI_DJ\data\tts_cache\` (synthesized audio files)
- **Music Library:** `C:\Users\AI\Desktop\mp3s` (your MP3 files)

## Command-Line Arguments

Currently none. Use environment variables for configuration:

```bash
set PLAYBACK_VOLUME=75 & set NEWS_ENABLED=false & python gui.py
```

## Next Steps

- **Customize Music Library** — Change path in config or move your MP3s
- **Adjust Commentary Length** — Edit `config.yaml` → `commentary.target_seconds`
- **Change News Cadence** — Edit `config.yaml` → `news.interval_minutes`
- **Add More Market Tickers** — Edit `config.yaml` → `market.tickers`
- **Optional: Web UI** — See Phase 9 for a browser-based control panel

## Notes

- The GUI runs the playback in a background thread, so it's responsive even during long operations
- Settings panel changes are not yet persisted to disk (they apply only to the current session)
- Future enhancements could include: volume ducking, crossfade, playlist management, search
