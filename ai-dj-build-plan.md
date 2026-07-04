# AI DJ Application — Build Plan

A self-hosted radio-station-style app that plays your local MP3s, talks between
tracks like a real DJ (artist trivia), and drops in news/market updates on a
schedule — powered by free-tier cloud LLMs, running in Docker on your Linux box.

---

## 1. Define the shape of the thing first

Before writing code, pin down these decisions — they drive everything downstream:

| Decision | Recommendation | Why |
|---|---|---|
| How is commentary delivered — spoken (TTS) or just text/log? | **Spoken (TTS)** | A DJ that only prints text isn't really a DJ. This is the single biggest architectural fork, so decide it now. |
| Where do MP3 tags/metadata come from? | ID3 tags in the files (`mutagen`) | You already have artist/title/album embedded; no need to guess. |
| How does playback actually happen? | `python-vlc` or `mpv` via `python-mpv` | Both handle gapless playback, volume ducking (fade music down while DJ talks), and run fine headless in a container. |
| Single always-on background service, or on-demand CLI? | **Background service** (systemd-style loop in the container), with a small local web UI for control | Matches the "radio station" mental model — it should just run. |

---

## 2. High-level architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Docker container(s)                   │
│                                                                │
│  ┌──────────────┐   ┌───────────────┐   ┌─────────────────┐  │
│  │ Playlist /    │──▶│ DJ Orchestrator│──▶│ Audio Player    │  │
│  │ Queue Manager │   │ (scheduler +   │   │ (mpv/vlc)       │  │
│  │ (reads MP3s,  │   │  state machine)│   │ ducks volume,   │  │
│  │  tags via     │   │                │   │ plays TTS clip, │  │
│  │  mutagen)     │   └───────┬───────┘   │ resumes music   │  │
│  └──────────────┘           │            └─────────────────┘  │
│                              ▼                                │
│                   ┌─────────────────────┐                     │
│                   │ Content Generators    │                    │
│                   │  • Artist fact fetcher│                    │
│                   │  • News summarizer    │                    │
│                   │  • Market summarizer  │                    │
│                   └──────────┬───────────┘                     │
│                              ▼                                │
│                   ┌─────────────────────┐                     │
│                   │  LLM client (free    │                    │
│                   │  tier, swappable)     │                    │
│                   └──────────┬───────────┘                     │
│                              ▼                                │
│                   ┌─────────────────────┐                     │
│                   │  TTS engine           │                    │
│                   └──────────┬───────────┘                     │
│                              ▼                                │
│                     back to Audio Player                       │
│                                                                │
│  ┌──────────────┐                                              │
│  │ Config store  │  (commentary length, on/off, schedule,      │
│  │ (SQLite/YAML) │   news cadence, voice, API keys)             │
│  └──────────────┘                                              │
└─────────────────────────────────────────────────────────────┘
        ▲
        │ optional lightweight web UI (FastAPI + a simple page)
        │ for skip/pause/config, reachable on your LAN
```

Keep each box as a separate Python module (not necessarily separate containers
— one container is fine to start). This matters most for vibe-coding, because
it lets you hand the AI coding tool one file at a time with a clear contract
("this module takes a song, returns a fact string") instead of one giant script.

---

## 3. Component-by-component choices

### Playback & metadata
- **`mutagen`** — read ID3/artist/title/album/year from MP3s. Zero cost, no API.
- **`python-mpv`** (wraps libmpv) — reliable gapless playback, volume control,
  fade in/out, works headless in Docker. `python-vlc` is a solid alternative
  if you're already comfortable with VLC.
- Maintain a simple **queue table** (SQLite) so "now playing," "up next," and
  "recently played" persist across restarts.

### Artist/band facts
- **Wikipedia REST API** (`https://en.wikipedia.org/api/rest_v1/page/summary/{title}`)
  — free, no key, no rate-limit headaches for personal use. Pull the summary
  extract, hand *that* to the LLM and ask it to condense into a punchy N-second
  radio blurb rather than asking the LLM to "know" the fact itself (this also
  reduces hallucination risk — you're summarizing a real source, not asking
  the model to recall trivia from memory).
- **MusicBrainz API** — free, no key required (just a required `User-Agent`
  header identifying your app) — good for disambiguating artist names and
  pulling structured info (formed year, genre, related acts) when Wikipedia's
  summary is thin.
- Skip IMDb — it doesn't have a free public API; Wikipedia + MusicBrainz cover
  music artists better anyway.
- **Cache every fact you fetch** (SQLite, keyed by artist) so you're not
  re-hitting Wikipedia/MusicBrainz or re-summarizing with the LLM every time a
  song repeats. This also protects your free-tier LLM quota.

### News & market updates
- **News**: pull headlines from **RSS feeds** (Reuters, AP, BBC, NPR all
  publish free RSS) rather than a "News API" product — RSS has no key, no rate
  limit, and no signup. Use `feedparser` to grab the latest items, then have
  the LLM condense 3–5 headlines into a short spoken summary.
- **Markets**: `yfinance` (free, no key, scrapes Yahoo Finance) for
  close-of-day index levels (S&P 500, Dow, Nasdaq) and any tickers you care
  about. Feed the raw numbers to the LLM with a prompt like "turn these
  numbers into a 15-second radio-style market wrap."
- Schedule these with **APScheduler** — e.g., market wrap fires once at market
  close, news fires every N minutes, both configurable.

### The LLM (free, cloud-hosted, not local)
Based on what's actually available right now (mid-2026), here's how I'd stack it:

| Provider | Why use it | Rough free limits |
|---|---|---|
| **Google Gemini API (Flash)** | Best all-around free tier — decent quality, huge context, handles summarization well | ~1,500 requests/day, no credit card |
| **Groq** | Backup/fallback — extremely fast, good for short commentary generation, OpenAI-compatible API | ~14,400 requests/day on open models like Llama 3.3 70B |
| **OpenRouter** | Widest model variety through one key, good fallback layer if Gemini or Groq rate-limits you | 28+ free models, ~20 req/min |

**Practical recommendation:** build a thin `LLMClient` wrapper class with one
method, `generate(prompt) -> str`, and make the actual provider swappable via
config. Start with Gemini as primary, Groq as automatic fallback if Gemini
errors or rate-limits. This is maybe 30 extra minutes of work up front and
saves you from ever being fully blocked when one provider's free tier tightens
(these change often — worth designing for that from day one rather than
hardcoding one provider).

All three are OpenAI-SDK-compatible or close to it, so the wrapper is simple:

```python
class LLMClient:
    def __init__(self, primary="gemini", fallback="groq"):
        ...
    def generate(self, prompt: str, max_tokens: int = 150) -> str:
        try:
            return self._call(self.primary, prompt, max_tokens)
        except (RateLimitError, ProviderError):
            return self._call(self.fallback, prompt, max_tokens)
```

### Text-to-speech (turning commentary into audio)
This wasn't in your original spec but is almost certainly what you want for a
"DJ" experience:
- **`edge-tts`** (Python package, uses Microsoft's free Edge neural voices) —
  free, no key, good quality, easy — this is the pragmatic default.
- **Piper TTS** — runs locally, free, no internet dependency, if you'd rather
  not send commentary text to a third party for speech synthesis. Since you
  said no *local LLM*, not no local anything, a local TTS engine is a
  reasonable middle ground and keeps the audio pipeline resilient if your
  network hiccups.
- Either way: generate the commentary MP3/WAV once, cache it, play it through
  the same `mpv`/`vlc` player, ducking the music bed under it if you want that
  classic "DJ talks over the fade" effect.

### Configuration
- A single **YAML or SQLite-backed config**: commentary on/off, commentary
  target length (in seconds or words), news cadence, market-wrap time, voice
  selection, per-provider API keys (read from environment variables /
  Docker secrets — never hardcoded).
- Expose it through a minimal **FastAPI** endpoint + a one-page HTML control
  panel if you want to tweak settings without editing files — optional but
  nice, and easy to vibe-code as a separate small module.

---

## 4. Step-by-step build order

Build in this order — each phase produces something you can actually run and
listen to, which keeps vibe-coding sessions grounded in a working artifact
rather than a pile of disconnected files.

1. **Bare playback loop.** Read a folder of MP3s, extract tags with `mutagen`,
   play them in order with `python-mpv`. No AI yet. Get this rock solid first.
2. **Queue + shuffle/rotation logic.** Add a proper queue (SQLite), basic
   shuffle, skip, and "now playing" state.
3. **Wire up the LLM client.** Build the swappable Gemini/Groq/OpenRouter
   wrapper as its own module, test it standalone with a throwaway script
   before integrating.
4. **Artist commentary.** Wikipedia/MusicBrainz fetch → LLM condense → cache
   in SQLite. Still text-only at this point — print it to the console and
   confirm the facts are good and the length setting is respected.
5. **Add TTS.** Take the commentary text, synthesize audio, play it before the
   next track starts. This is where it starts to feel like a real DJ.
6. **News + market modules.** RSS pull + `yfinance` pull → LLM summarize →
   TTS → scheduled insertion into the queue via APScheduler.
7. **Config layer + on/off toggles.** Make commentary length, news cadence,
   and enable/disable flags live in config rather than hardcoded.
8. **Containerize.** Write the Dockerfile, mount your MP3 library as a
   read-only volume, mount a data volume for the SQLite cache/queue state,
   pass API keys via environment variables or Docker secrets.
9. **(Optional) Web control panel.** Small FastAPI app for skip/pause/volume
   and editing config live.
10. **Polish pass.** Volume ducking/crossfade, graceful handling of API
    rate-limit errors (fall back to "no commentary this track" rather than
    crashing the stream), logging.

---

## 5. Docker notes specific to this app

- Base image: `python:3.12-slim`, then `apt-get install` `mpv` (or `vlc`) plus
  its audio libs.
- Audio output from inside a container is the one genuinely fiddly part on
  Linux — you'll want to pass through PulseAudio or ALSA from the host
  (`-v /run/user/1000/pulse:/run/user/1000/pulse` and the matching env var is
  the common pattern, or route through PipeWire's Pulse-compat socket if
  that's what your Linux setup uses). Worth solving this in phase 1 before
  building anything on top of it.
- Mount MP3 library read-only: `-v /path/to/music:/music:ro`
- Mount a data volume for the SQLite DB (queue/cache/config):
  `-v ai-dj-data:/data`
- API keys via `--env-file .env` or Docker secrets, never baked into the image.

---

## 6. Vibe-coding tool recommendation

Given you're already comfortable with Python, Docker, and Linux, the tool that
fits this project best is **Claude Code** — it runs from your terminal (or
desktop/VS Code), can read and write files across your whole project
directory, run your Docker builds, and iterate against real error output
instead of you copy-pasting between a chat window and your editor. That
matters a lot here because this project has real integration points to
debug — audio device passthrough in Docker, API rate-limit handling, TTS
playback timing — which go faster when the tool can actually run commands and
see the output rather than just generating code blind.

Practical workflow:
- Start a scratch repo, describe phase 1 (bare playback loop) in plain
  language, let it write and test the code against your actual MP3 folder.
- Move phase-by-phase through the build order above — each phase as its own
  focused session/prompt keeps the AI's context tight and the output easier
  to review.
- Keep the LLM-provider wrapper and the TTS module as isolated files you can
  hand over individually ("here's `llm_client.py`, add an OpenRouter fallback
  path") rather than re-pasting your whole codebase each time.

I'll flag it below via the app suggestion so you have the install link handy.
