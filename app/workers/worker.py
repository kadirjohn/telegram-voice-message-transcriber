from __future__ import annotations

import signal
import sys

import structlog
from rq import Connection, Worker
from rq.worker import WorkerStatus

from app.config import get_settings
from app.logging import configure_logging, get_logger
from app.queue import create_redis_connection

logger: structlog.stdlib.BoundLogger = get_logger(__name__)


def run_worker() -> None:
    """Entry point for the RQ worker process."""
    configure_logging()
    settings = get_settings()

    redis_conn = create_redis_connection()
    queue_names = [settings.RQ_QUEUE_NAME]

    with Connection(redis_conn):
        worker = Worker(
            queues=queue_names,
            name=f"worker-{settings.APP_ENV}",
            default_worker_ttl=420,
        )

        # Enable scheduler for delayed jobs (model fallback retries)
        worker.work_with_scheduler()

    logger.info(
        "worker_starting",
        queues=queue_names,
        env=settings.APP_ENV,
    )

    # Handle graceful shutdown
    def _shutdown(signum: int, _frame: object) -> None:
        logger.info("worker_shutdown_requested", signal=signum)
        if worker.state == WorkerStatus.IDLE:
            sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    worker.work_with_scheduler()
