# AI DJ: self-hosted radio station with artist commentary, news, and markets.
# Multi-stage build to keep the final image lean.

FROM python:3.12-slim as builder
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.12-slim
# Install VLC and audio libraries for playback.
# PulseAudio/ALSA are optional but recommended for audio passthrough from the host.
RUN apt-get update && apt-get install -y --no-install-recommends \
    vlc \
    libvlc-dev \
    libpulse0 \
    alsa-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# Copy Python dependencies from builder stage.
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy app code.
COPY *.py ./
COPY config.yaml.example ./config.yaml.example

# Create directories for mounted volumes.
RUN mkdir -p /music /data/tts_cache

# No entrypoint hardcoded; docker-compose specifies the command.
# This allows flexibility (e.g., running just "python -c" for setup).
CMD ["python", "main.py"]
