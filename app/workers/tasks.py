from __future__ import annotations

import uuid
from datetime import timedelta

import structlog

from app.config import get_settings
from app.db.enums import JobStatus
from app.db.repositories.job_repository import JobRepository
from app.logging import get_logger
from app.queue import create_queue, transcription_job_timeout
from app.services.exceptions import (
    EmptyTranscriptError,
    NoSpeechDetectedError,
    SuspiciousTranscriptError,
    UstaGPTAuthError,
    UstaGPTPermanentError,
    UstaGPTTemporaryError,
)
from app.services.speech_audio import SpeechAudioService
from app.services.telegram_files import TelegramFileService
from app.services.transcript_delivery import TranscriptDeliveryService
from app.services.transcript_quality import validate_transcript
from app.services.ustagpt_client import UstaGPTClient

logger: structlog.stdlib.BoundLogger = get_logger(__name__)


def process_transcription_job(job_id: str, model_index: int = 0) -> None:
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
        job_repo.close()
        return
    if job.status in (JobStatus.SUCCEEDED, JobStatus.CANCELLED):
        job_repo.close()
        return

    settings = get_settings()
    file_service = TelegramFileService()
    temp_dir = None

    try:
        temp_dir = file_service.create_temp_dir()
        # Download
        job_repo.update_status(job_uuid, JobStatus.DOWNLOADING)
        downloaded = file_service.download_file(job.telegram_file_id, temp_dir)
        log.info("file_downloaded", path=str(downloaded))

        # Decode losslessly, remove non-speech, and bound each API upload.
        job_repo.update_status(job_uuid, JobStatus.CONVERTING)
        chunks = SpeechAudioService().prepare_chunks(downloaded, temp_dir)
        log.info("speech_prepared", chunks=len(chunks))

        # Resolve model chain
        model_chain = job.model_chain or []
        if not model_chain:
            from app.services.model_chain import default_model_chain

            model_chain = default_model_chain()

        client = UstaGPTClient()
        transcript = None
        successful_model = None
        last_error = None

        for attempt_idx in range(model_index, len(model_chain)):
            model = model_chain[attempt_idx]
            attempt_no = attempt_idx + 1
            job_repo.set_current_attempt(job_uuid, attempt_no)
            log.info("transcription_attempt", model=model, attempt=attempt_no)

            job_repo.update_status(job_uuid, JobStatus.TRANSCRIBING)

            try:
                language = job.language or settings.USTAGPT_LANGUAGE
                lang_param = language if language != "auto" else None

                texts = []
                for chunk in chunks:
                    text = client.transcribe(
                        audio_path=chunk.path,
                        model=model,
                        language=lang_param,
                    )
                    texts.append(validate_transcript(text, chunk.duration_seconds))
                transcript = "\n".join(texts)
                successful_model = model
                log.info("transcription_success", model=model)
                break

            except UstaGPTAuthError as exc:
                log.error("auth_error", model=model, error=str(exc))
                job_repo.update_status(job_uuid, JobStatus.FAILED)
                _notify_auth_failure(job, str(exc))
                _notify_failure(job, "Transkripsiyon servisine erişilemiyor.")
                return

            except (EmptyTranscriptError, SuspiciousTranscriptError) as exc:
                # A 2xx response is not enough: never deliver obvious loops or
                # an implausibly long output. Re-transcribe with another model.
                last_error = str(exc)
                log.warning("transcript_rejected", model=model, error=last_error)
                continue

            except UstaGPTTemporaryError as exc:
                last_error = str(exc)
                log.warning("retriable_error", model=model, error=last_error)

                if attempt_idx < len(model_chain) - 1:
                    # Schedule next attempt with next model after 30 seconds
                    job_repo.update_status(job_uuid, JobStatus.RETRY_WAIT)
                    queue = create_queue()
                    queue.enqueue_in(
                        timedelta(seconds=settings.USTAGPT_RETRY_DELAY_SECONDS),
                        "app.workers.tasks.process_transcription_job",
                        job_id,
                        attempt_idx + 1,
                        job_timeout=transcription_job_timeout(
                            job.duration_seconds,
                            model_count=len(model_chain) - attempt_idx - 1,
                        ),
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

        # Edit the existing status; send only overflow as further replies.
        delivery = TranscriptDeliveryService()
        delivery.deliver_transcript(
            chat_id=job.chat_id,
            reply_to_message_id=job.source_message_id,
            status_message_id=job.status_message_id,
            transcript=transcript,
            thread_id=job.source_thread_id,
            model=successful_model,
            show_footer=settings.SHOW_MODEL_FOOTER,
        )

        job_repo.update_status(job_uuid, JobStatus.SUCCEEDED)
        log.info("job_completed")

    except NoSpeechDetectedError:
        job_repo.update_status(job_uuid, JobStatus.CANCELLED)
        delivery = TranscriptDeliveryService()
        if job.status_message_id:
            delivery.edit_status(
                job.chat_id,
                job.status_message_id,
                "🔇 Bu kayıtta yeterli konuşma algılanamadı. "
                "Daha net bir ses kaydı gönderebilirsiniz.",
            )
        log.info("job_no_speech")
    except Exception as exc:
        log.error("job_crashed", error=str(exc))
        job_repo.update_status(job_uuid, JobStatus.FAILED)
        _notify_failure(job, "İş tamamlanamadı")
    finally:
        if temp_dir is not None:
            file_service.cleanup_temp_dir(temp_dir)
        job_repo.close()
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
