# AI DJ — Intelligent Music Player with AI Commentary & News

A Windows desktop music player that uses AI to generate personalized DJ commentary, news briefs, and market updates while playing your music collection.

## Features

🎵 **Smart Music Playback**
- Queue management with ratings (👍👎) to influence playback frequency
- Album art display with fallback to Wikipedia artist images
- Scrollable playlist and play history
- Keyboard shortcuts (Spacebar for play/pause, arrows for skip/volume)

🎤 **AI DJ Personas**
- Create multiple DJ profiles with custom:
  - Stage name, station name, voice, tone, and speed
  - Demographics (gender, generation, orientation) → auto-mapped to 11 Edge TTS voices
  - Profile pictures (200×260 display)
  - News source preferences (14+ RSS feeds available)

📰 **AI-Generated Content**
- **Commentary**: Per-artist trivia + song announcements via LLM (Gemini/Groq)
- **News Briefs**: Configurable RSS feeds, synthesized to speech
- **Market Updates**: Stock ticker summaries at configured times
- **Pre-rendering**: News/commentary synthesized during playback → no dead air

🔧 **Advanced Controls**
- Content toggle switches (Commentary/News/Markets on/off)
- Per-DJ news reading speed (0.5×–1.5×)
- Music directory selection with automatic scanning
- Settings persistence via YAML config

📦 **Standalone Executable**
- Windows 10+ (64-bit) — no Python required
- Fully portable (USB drive friendly)
- System tray integration with Pause/Skip/Exit controls

## Installation

### Option 1: Pre-built Executable (Easiest)

1. Download the latest `AI_DJ.zip` from [Releases](https://github.com/JW2WW/Radio-DJ-for-MP3s/releases)
2. Extract to any folder
3. Double-click `AI_DJ/AI_DJ.exe`
4. Create/select a DJ and choose your music directory
5. Done!

**Optional:** Create `.env` file in the `AI_DJ` folder for AI features:
```
GEMINI_API_KEY=your-key-here
GROQ_API_KEY=your-groq-key (fallback)
```

Get free API keys:
- [Google AI Studio](https://aistudio.google.com/app/apikey) (Gemini)
- [Groq Console](https://console.groq.com/) (Groq)

### Option 2: Run from Source

**Requirements:**
- Python 3.10+
- Windows 10+ (64-bit)
- pip

**Setup:**
```bash
git clone https://github.com/JW2WW/Radio-DJ-for-MP3s.git
cd Radio-DJ-for-MP3s
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

## Usage

### First Launch
1. **Select DJ** — Pick or create a DJ persona
2. **Choose Directory** — Browse to your music folder (contains .mp3 files)
3. **Configure (Optional)** — Customize news sources, speeds, etc. via 🎤 DJs button

### During Playback
- **Play/Pause**: Spacebar
- **Skip**: → or ⏭ button
- **Volume**: ↑/↓ or slider
- **Toggle Content**: Use checkboxes (Commentary/News/Markets)
- **Rate Track**: 👍/👎 buttons
- **Change Directory**: 📁 button
- **Manage DJs**: 🎤 button

### Settings
- `config.yaml` — Generated on first run, edit for:
  - Default volume, playback preferences
  - Commentary/News/Market enable/disable
  - News fetch interval, target durations

## Architecture

```
app.py                    → Entry point, DJ selection, music directory
gui_enhanced.py           → Main playback GUI, playlist/history tabs
playback_controller.py    → Background playback thread, queue management
queue_manager.py          → SQLite queue with ratings, shuffle logic
dj_profile.py             → DJ personas, voice mapping
commentary.py             → LLM-powered artist trivia with caching
news_fetcher.py           → RSS feed fetching + LLM news condensing
tts.py                    → Microsoft Edge TTS with caching
player.py                 → VLC media player wrapper
artist_images.py          → Album art extraction + Wikipedia fallback
dj_manager_ui.py          → DJ creation/editing UI
dj_selector.py            → Initial DJ selection screen
music_directory.py        → Directory picker
paths.py                  → Cross-platform path resolution (dev + exe)
sqlite_db.py              → Shared SQLite WAL connections + locking
```

## Key Technologies

- **GUI**: Tkinter (native Windows)
- **Playback**: python-vlc (VLC engine)
- **TTS**: Microsoft Edge TTS (edge-tts)
- **LLM**: Google Gemini / Groq (commentary + news)
- **RSS**: feedparser
- **Images**: PIL/Pillow + Wikipedia API
- **Database**: SQLite
- **Bundling**: PyInstaller (exe generation)

## News Sources

14+ configurable RSS feeds:
- **US News**: NPR, CNN, Fox News, ABC News, NBC News, New York Times, LA Times, CNBC, Washington Times
- **International**: BBC, The Guardian, Al Jazeera
- **Tech**: Hacker News

## Threading & Performance

- **Non-blocking playback**: Playback in background thread, GUI responsive
- **Thread-safe SQLite**: Check-same-thread disabled + explicit locking
- **Pre-rendering**: News/commentary synthesized during current song (eliminates gaps)
- **Polling-based commands**: Pause/Skip/Volume processed during playback with 0.1s latency

## Building the Executable

```bash
pip install pyinstaller
pyinstaller ai_dj.spec
```

Output: `dist/AI_DJ/AI_DJ.exe` (70 MB, includes Python runtime)

## Running Tests

```bash
pip install -r requirements.txt
pytest
```

## Known Limitations

- **Windows only** (Tkinter + pystray + VLC quirks)
- **MP3 files only** (easily extended to FLAC/WAV)
- **Internet required** for news/commentary (caches aggressively)
- **API quota limits** (Gemini free tier ~50 API calls/day; Groq ~14k/min)

## Future Ideas

- [ ] macOS/Linux support (Qt instead of Tkinter)
- [ ] Web UI (FastAPI + React)
- [ ] Playlist import/export (M3U, PLIST)
- [ ] Last.fm scrobbling
- [ ] Voice control (hotword + TTS response)
- [ ] More LLM providers (Claude, OpenAI)
- [ ] Real-time voice synthesis (lower latency than edge-tts)

## Contributing

Contributions welcome! Areas of interest:
- Cross-platform improvements
- UI/UX enhancements
- Additional LLM/TTS providers
- Test coverage
- Documentation

## License

MIT License — see [LICENSE](LICENSE)

## Author

Built with ❤️ by [JW2WW](https://github.com/JW2WW)

---

**Have questions?** Open an [Issue](https://github.com/JW2WW/Radio-DJ-for-MP3s/issues) or [Discussion](https://github.com/JW2WW/Radio-DJ-for-MP3s/discussions)

**Want to support?** ⭐ Star the repo, or [sponsor](https://github.com/sponsors/JW2WW) the project
