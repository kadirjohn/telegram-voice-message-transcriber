from __future__ import annotations

from math import ceil

import redis as redis_lib
from rq import Queue

from app.config import get_settings


def transcription_job_timeout(
    duration_seconds: int | None, *, model_count: int = 4
) -> int:
    """Allow time for bounded uploads instead of timing out long recordings."""
    settings = get_settings()
    duration = duration_seconds or settings.MAX_VOICE_DURATION_SECONDS
    # PCM uses 32,000 bytes/second; preparation aligns blocks to 30 ms frames.
    max_frames = min(
        int(settings.AUDIO_CHUNK_SECONDS / 0.03),
        (settings.MAX_VOICE_FILE_BYTES - 44) // 960,
    )
    chunk_seconds = max(1, max_frames) * 0.03
    # Pause boundaries can shorten each block by up to three seconds.
    effective_seconds = max(0.03, chunk_seconds - min(3, chunk_seconds - 0.03))
    chunks = ceil(duration / effective_seconds)
    request_seconds = (
        settings.USTAGPT_CONNECT_TIMEOUT_SECONDS
        + 2 * settings.USTAGPT_READ_TIMEOUT_SECONDS
        + 10
    )
    return max(
        600,
        settings.FFMPEG_TIMEOUT_SECONDS
        + 120
        + chunks * max(1, model_count) * request_seconds,
    )


def create_redis_connection() -> redis_lib.Redis:
    """Create a Redis connection from application settings."""
    settings = get_settings()
    return redis_lib.from_url(
        settings.REDIS_URL,
        decode_responses=False,
        socket_connect_timeout=5,
        socket_timeout=10,
        retry_on_timeout=True,
        health_check_interval=30,
    )


def create_queue() -> Queue:
    """Create the RQ transcription queue."""
    settings = get_settings()
    connection = create_redis_connection()
    return Queue(
        name=settings.RQ_QUEUE_NAME,
        connection=connection,
        default_timeout=600,
        result_ttl=0,
    )
