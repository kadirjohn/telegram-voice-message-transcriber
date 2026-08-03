from __future__ import annotations

import redis as redis_lib
from rq import Queue

from app.config import get_settings


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
