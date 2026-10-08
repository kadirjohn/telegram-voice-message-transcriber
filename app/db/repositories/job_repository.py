from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.enums import JobStatus
from app.db.models.transcription_job import TranscriptionJob
from app.db.session import get_session


class JobRepository:
    """Data access for transcription_jobs."""

    def __init__(self, session: Session | None = None) -> None:
        self._session = session or get_session()

    def get_by_id(self, job_id: uuid.UUID) -> TranscriptionJob | None:
        return self._session.get(TranscriptionJob, job_id)

    def get_by_chat_message(
        self, chat_id: int, message_id: int
    ) -> TranscriptionJob | None:
        stmt = (
            select(TranscriptionJob)
            .where(
                TranscriptionJob.chat_id == chat_id,
                TranscriptionJob.source_message_id == message_id,
            )
            .limit(1)
        )
        return self._session.scalar(stmt)

    def create(
        self,
        chat_id: int,
        source_message_id: int,
        sender_telegram_id: int,
        telegram_file_id: str,
        telegram_file_unique_id: str,
        *,
        source_thread_id: int | None = None,
        duration_seconds: float | None = None,
        file_size: int | None = None,
        mime_type: str | None = None,
        language: str | None = None,
        model_chain: list[str] | None = None,
    ) -> TranscriptionJob:
        job = TranscriptionJob(
            id=uuid.uuid4(),
            chat_id=chat_id,
            source_message_id=source_message_id,
            source_thread_id=source_thread_id,
            sender_telegram_id=sender_telegram_id,
            telegram_file_id=telegram_file_id,
            telegram_file_unique_id=telegram_file_unique_id,
            duration_seconds=duration_seconds,
            file_size=file_size,
            mime_type=mime_type,
            language=language,
            model_chain=model_chain,
            status=JobStatus.QUEUED,
        )
        self._session.add(job)
        self._session.commit()
        return job

    def set_status_message_id(self, job_id: uuid.UUID, status_message_id: int) -> None:
        stmt = (
            update(TranscriptionJob)
            .where(TranscriptionJob.id == job_id)
            .values(status_message_id=status_message_id)
        )
        self._session.execute(stmt)
        self._session.commit()

    def update_status(
        self, job_id: uuid.UUID, status: JobStatus
    ) -> TranscriptionJob | None:
        job = self.get_by_id(job_id)
        if job is None:
            return None
        job.status = status
        if status == JobStatus.SUCCEEDED:
            job.completed_at = datetime.now(UTC)
        self._session.commit()
        return job

    def set_current_attempt(self, job_id: uuid.UUID, attempt: int) -> None:
        stmt = (
            update(TranscriptionJob)
            .where(TranscriptionJob.id == job_id)
            .values(current_attempt=attempt)
        )
        self._session.execute(stmt)
        self._session.commit()

    def close(self) -> None:
        self._session.close()

    def get_failed(self) -> list[TranscriptionJob]:
        stmt = (
            select(TranscriptionJob)
            .where(TranscriptionJob.status == JobStatus.FAILED)
            .order_by(TranscriptionJob.created_at.desc())
        )
        return list(self._session.scalars(stmt).all())
