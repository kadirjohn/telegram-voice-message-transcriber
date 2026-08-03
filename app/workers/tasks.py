from __future__ import annotations

import uuid

import structlog

from app.config import get_settings
from app.db.enums import JobStatus
from app.db.repositories.job_repository import JobRepository
from app.logging import get_logger
from app.queue import create_queue
from app.services.audio_converter import AudioConverter
from app.services.exceptions import (
    EmptyTranscriptError,
    UstaGPTAuthError,
    UstaGPTPermanentError,
    UstaGPTTemporaryError,
)
from app.services.telegram_files import TelegramFileService
from app.services.transcript_delivery import TranscriptDeliveryService
from app.services.ustagpt_client import UstaGPTClient

logger: structlog.stdlib.BoundLogger = get_logger(__name__)


def process_transcription_job(job_id: str) -> None:
    """RQ job: download, convert, transcribe with fallback, and deliver."""
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

    settings = get_settings()
    file_service = TelegramFileService()
    temp_dir = file_service.create_temp_dir()

    try:
        # Download
        job_repo.update_status(job_uuid, JobStatus.DOWNLOADING)
        downloaded = file_service.download_file(job.telegram_file_id, temp_dir)
        log.info("file_downloaded", path=str(downloaded))

        # Convert
        job_repo.update_status(job_uuid, JobStatus.CONVERTING)
        converter = AudioConverter()
        mp3_path = converter.convert_to_mp3(downloaded, temp_dir)
        log.info("file_converted", path=str(mp3_path))

        # Resolve model chain
        model_chain = job.model_chain or []
        if not model_chain:
            from app.services.model_chain import default_model_chain
            model_chain = default_model_chain()

        client = UstaGPTClient()
        transcript = None
        last_error = None

        for attempt_idx, model in enumerate(model_chain):
            attempt_no = attempt_idx + 1
            log.info("transcription_attempt", model=model, attempt=attempt_no)

            job_repo.update_status(job_uuid, JobStatus.TRANSCRIBING)

            try:
                language = job.language or settings.USTAGPT_LANGUAGE
                lang_param = language if language != "auto" else None

                transcript = client.transcribe(
                    audio_path=mp3_path,
                    model=model,
                    language=lang_param,
                )
                log.info("transcription_success", model=model)
                break

            except UstaGPTAuthError as exc:
                log.error("auth_error", model=model, error=str(exc))
                job_repo.update_status(job_uuid, JobStatus.FAILED)
                _notify_auth_failure(job, str(exc))
                return

            except (UstaGPTTemporaryError, EmptyTranscriptError) as exc:
                last_error = str(exc)
                log.warning("retriable_error", model=model, error=last_error)

                if attempt_idx < len(model_chain) - 1:
                    # Schedule next attempt with next model after 30 seconds
                    job_repo.update_status(job_uuid, JobStatus.RETRY_WAIT)
                    queue = create_queue()
                    queue.enqueue_in(
                        time_delta=settings.USTAGPT_RETRY_DELAY_SECONDS,
                        func="app.workers.tasks.process_transcription_job",
                        args=(job_id,),
                        job_id=f"tg:{job.chat_id}:{job.source_message_id}",
                        job_timeout=600,
                        result_ttl=0,
                    )
                    log.info("scheduled_retry", next_model=model_chain[attempt_idx + 1])
                    return

            except UstaGPTPermanentError as exc:
                last_error = str(exc)
                log.warning("permanent_error", model=model, error=last_error)
                continue

        if transcript is None:
            job_repo.update_status(job_uuid, JobStatus.FAILED)
            _notify_failure(job, last_error or "All models failed")
            return

        # Deliver transcript
        delivery = TranscriptDeliveryService()
        chat_id = job.chat_id
        reply_id = job.source_message_id
        status_msg_id = job.status_message_id

        if status_msg_id:
            delivery.edit_status(chat_id, status_msg_id, transcript[:4096])

        delivery.send_transcript(
            chat_id=chat_id,
            reply_to_message_id=reply_id,
            transcript=transcript,
            thread_id=job.source_thread_id,
            model=model_chain[-1] if transcript else None,
            show_footer=settings.SHOW_MODEL_FOOTER,
        )

        job_repo.update_status(job_uuid, JobStatus.SUCCEEDED)
        log.info("job_completed")

    except Exception as exc:
        log.error("job_crashed", error=str(exc))
        job_repo.update_status(job_uuid, JobStatus.FAILED)
    finally:
        file_service.cleanup_temp_dir(temp_dir)
        log.info("temp_dir_cleaned")


def _notify_auth_failure(job, error_msg: str) -> None:
    """Notify the owner about an API authentication failure."""
    log = logger.bind(job_id=str(job.id))
    log.error("auth_failure_notified", error=error_msg)


def _notify_failure(job, error_msg: str) -> None:
    """Mark the job as failed and notify the user."""
    log = logger.bind(job_id=str(job.id))
    log.error("job_failed", error=error_msg)

    delivery = TranscriptDeliveryService()
    short_id = str(job.id)[:8]
    text = f"❌ Sesli mesaj çevrilemedi. İş kodu: {short_id}"

    if job.status_message_id:
        delivery.edit_status(job.chat_id, job.status_message_id, text)
