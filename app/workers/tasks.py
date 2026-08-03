from __future__ import annotations

import uuid

import structlog

from app.db.enums import JobStatus
from app.db.repositories.job_repository import JobRepository
from app.logging import get_logger
from app.services.audio_converter import AudioConverter
from app.services.telegram_files import TelegramFileService

logger: structlog.stdlib.BoundLogger = get_logger(__name__)


def process_transcription_job(job_id: str) -> None:
    """RQ job: download voice message, convert to MP3, and prepare for transcription."""
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

    # Mark as downloading
    job_repo.update_status(job_uuid, JobStatus.DOWNLOADING)
    log.info("job_downloading")

    file_service = TelegramFileService()
    temp_dir = file_service.create_temp_dir()

    try:
        # Download the voice file from Telegram
        downloaded = file_service.download_file(job.telegram_file_id, temp_dir)
        dl_size = downloaded.stat().st_size
        log.info("file_downloaded", path=str(downloaded), size=dl_size)

        # Mark as converting
        job_repo.update_status(job_uuid, JobStatus.CONVERTING)
        log.info("job_converting")

        # Convert OGG to MP3
        converter = AudioConverter()
        mp3_path = converter.convert_to_mp3(downloaded, temp_dir)
        log.info("file_converted", path=str(mp3_path), size=mp3_path.stat().st_size)

        # Mark as transcribing (placeholder for Phase 6)
        job_repo.update_status(job_uuid, JobStatus.TRANSCRIBING)
        log.info("job_ready_for_transcription", mp3_path=str(mp3_path))

    except Exception as exc:
        log.error("job_processing_failed", error=str(exc))
        job_repo.update_status(job_uuid, JobStatus.FAILED)
    finally:
        file_service.cleanup_temp_dir(temp_dir)
        log.info("temp_dir_cleaned")
