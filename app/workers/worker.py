from __future__ import annotations

import signal
import sys

import structlog
from rq import Worker
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

    worker = Worker(
        queues=queue_names,
        connection=redis_conn,
        name=f"worker-{settings.APP_ENV}",
        worker_ttl=420,
    )

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

    # with_scheduler=True is required: retryable errors are rescheduled with
    # enqueue_in(), and RQ's work() defaults to with_scheduler=False. Without
    # the scheduler those delayed jobs stay in rq:scheduled:<queue> forever and
    # are never moved into the queue, so every retried job hangs in RETRY_WAIT.
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    run_worker()
