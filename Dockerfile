# ── Build stage ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY pyproject.toml .

RUN pip install --upgrade pip && \
    pip install .

# ── Runtime stage ────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production

# Install runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r transcriber && \
    useradd -r -g transcriber -d /app -s /sbin/nologin transcriber && \
    mkdir -p /app && \
    chown transcriber:transcriber /app

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=transcriber:transcriber . .

# Create writable temp directory
RUN mkdir -p /tmp/telegram-voice-transcriber && \
    chown transcriber:transcriber /tmp/telegram-voice-transcriber

USER transcriber

CMD ["python", "-m", "app.main"]
