from __future__ import annotations

import uuid

import structlog

from app.db.enums import JobStatus
from app.db.repositories.job_repository import JobRepository
from app.logging import get_logger

logger: structlog.stdlib.BoundLogger = get_logger(__name__)


def process_transcription_job(job_id: str) -> None:
    """RQ job: process a transcription job.

    This is the main worker entry point. It will be expanded in Phase 5-7
    with Telegram file download, FFmpeg conversion, and UstaGPT API calls.
    """
    log = logger.bind(job_id=job_id)
    log.info("job_started")

    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        log.error("job_invalid_uuid")
        return

    job_repo = JobRepository()
    job = job_repo.get_by_id(job_uuid)
    if job is None:
        log.error("job_not_found")
        return

    # Mark as downloading (placeholder — real logic in Phase 5)
    job_repo.update_status(job_uuid, JobStatus.DOWNLOADING)
    log.info("job_downloading")

    # Placeholder: will be replaced with actual processing
    job_repo.update_status(job_uuid, JobStatus.SUCCEEDED)
    log.info("job_completed_placeholder")
