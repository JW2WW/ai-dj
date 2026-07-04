# AI DJ Docker Deployment

This guide covers building and running the AI DJ app in Docker for self-hosted deployment on Linux, macOS, or Docker Desktop.

## Prerequisites

- Docker and Docker Compose installed
- API keys for Gemini and/or Groq (see `.env.example`)
- A folder of MP3 files on your host machine

## Quick Start

1. **Create `.env` with your API keys:**
   ```bash
   cp .env.example .env
   # Edit .env and add your GEMINI_API_KEY and/or GROQ_API_KEY
   ```

2. **Update `docker-compose.yml` with your music library path:**
   ```yaml
   volumes:
     - /path/to/your/mp3s:/music:ro  # Change this path
     - ai-dj-data:/data
   ```

3. **Start the container:**
   ```bash
   docker-compose up -d
   ```

4. **View logs:**
   ```bash
   docker-compose logs -f ai-dj
   ```

5. **Stop the container:**
   ```bash
   docker-compose down
   ```

## Audio Passthrough Setup

The tricky part: getting audio out of the container. Choose the right option for your setup:

### Option A: Linux with PulseAudio (Desktop, most common)

Uncomment in `docker-compose.yml`:
```yaml
volumes:
  - /run/user/1000/pulse:/run/user/1000/pulse
environment:
  PULSE_SERVER: unix:/run/user/1000/pulse/native
```

Then start: `docker-compose up -d`

**How it works:** PulseAudio socket from your host is mounted into the container, so VLC can send audio to your desktop speakers.

### Option B: Linux with ALSA (Headless servers)

Uncomment in `docker-compose.yml`:
```yaml
devices:
  - /dev/snd:/dev/snd
```

Then start: `docker-compose up -d`

**How it works:** Direct audio device passthrough. Works on headless servers or minimal installs.

### Option C: Docker Desktop (Windows/macOS)

Docker Desktop on Windows/Mac runs Linux in a Hyper-V VM, and audio passthrough is tricky. Best options:

1. **SSH audio forwarding (advanced):** Set up X11/PulseAudio forwarding to your host machine.
2. **Run locally instead:** Use the native Windows/Mac setup (see project README).
3. **Stream audio over HTTP (future):** Output to a local HTTP stream instead of local audio device.

For now, Docker deployment is optimized for Linux with PulseAudio or ALSA.

## Configuration

### Via Environment Variables

Override any config setting at container startup:

```bash
docker-compose up -d \
  -e PLAYBACK_VOLUME=70 \
  -e COMMENTARY_TARGET_SECONDS=20 \
  -e NEWS_ENABLED=false \
  -e MARKET_TIME=16:00
```

Or add to `docker-compose.yml`:
```yaml
environment:
  PLAYBACK_VOLUME: "70"
  COMMENTARY_TARGET_SECONDS: "20"
```

### Via `config.yaml`

Mount a custom config file:
```yaml
volumes:
  - ./config.yaml:/app/config.yaml:ro
```

## Data Persistence

The `ai-dj-data` volume stores:
- SQLite database (queue state, cache)
- TTS audio files (synthesized commentary, news, market updates)
- Commentary cache

These persist across container restarts. To clear:
```bash
docker volume rm ai-dj-data
docker-compose up -d
```

## Building the Image

Rebuild after code changes:
```bash
docker-compose build
docker-compose up -d
```

Or manually:
```bash
docker build -t ai-dj:latest .
```

## Troubleshooting

### No audio output

- **PulseAudio:** Check `/run/user/1000/pulse` exists and is accessible.
  ```bash
  ls -la /run/user/1000/pulse
  ```
  If missing, PulseAudio may not be running on your host. Start it: `pulseaudio --start`

- **ALSA:** Check `/dev/snd` exists and has the right permissions.
  ```bash
  ls -la /dev/snd
  ```

- **Check VLC in the container:**
  ```bash
  docker exec ai-dj vlc --version
  ```

### Container exits immediately

Check logs:
```bash
docker-compose logs ai-dj
```

Common issues:
- Missing API keys in `.env`
- Music library path doesn't exist or is empty
- Config file has syntax errors

### Slow TTS or news fetches

The first fetch of commentary/news is slower (API call + LLM). Subsequent plays use cached files, which are instant. This is normal.

## Advanced: Docker Swarm or Kubernetes

For production orchestration, use Docker Compose as a template:
- Add resource limits (`deploy.resources.limits`)
- Use Docker secrets for API keys (instead of `.env`)
- Mount volumes via named drivers or NFS
- Set `restart_policy` for automatic recovery

Example Swarm setup:
```bash
echo $GEMINI_API_KEY | docker secret create gemini_api_key -
docker stack deploy -c docker-compose.yml ai-dj
```

Then reference in `docker-compose.yml`:
```yaml
environment:
  GEMINI_API_KEY_FILE: /run/secrets/gemini_api_key
```

(Would require code changes to read from the file.)

## Performance Notes

- **CPU:** Minimal (mostly I/O waiting on music, APIs). Runs fine on single-core.
- **RAM:** ~300MB base + VLC + Python overhead. 512MB safe, 1GB comfortable.
- **Disk:** 10GB+ for `ai-dj-data` if you cache years of news/market updates.
- **Network:** Brief spikes for API calls (LLM, news, market data). No sustained bandwidth needed.

## Typical Usage

```bash
# Start in the background
docker-compose up -d

# Check it's running
docker-compose ps

# View live logs
docker-compose logs -f ai-dj

# Configuration changes: edit .env or docker-compose.yml, then restart
docker-compose restart ai-dj

# Clean shutdown
docker-compose down

# Full cleanup (removes volumes)
docker-compose down -v
```

## Next Steps

- Set up a systemd service to auto-start the container on boot
- Add monitoring/alerting (watch Docker logs, alert on crashes)
- Customize the music library path, news feeds, market tickers in `config.yaml`
- Optional: Phase 9 (web control panel) for remote skip/pause/config
