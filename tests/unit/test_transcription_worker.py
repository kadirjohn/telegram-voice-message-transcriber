from __future__ import annotations

import uuid
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.db.enums import JobStatus
from app.services.exceptions import (
    NoSpeechDetectedError,
    TelegramDeliveryError,
    UstaGPTTemporaryError,
)
from app.services.model_chain import default_model_chain
from app.services.speech_audio import AudioChunk
from app.workers import tasks


@pytest.fixture
def worker_context(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SimpleNamespace:
    job = SimpleNamespace(
        id=uuid.uuid4(),
        chat_id=-100,
        source_message_id=10,
        source_thread_id=None,
        status_message_id=11,
        telegram_file_id="file",
        duration_seconds=30,
        model_chain=["gpt-4o-transcribe", "gpt-4o-mini-transcribe", "whisper-1"],
        language="auto",
        status=JobStatus.QUEUED,
    )
    repo = MagicMock()
    repo.get_by_id.return_value = job

    def update_status(_job_id: uuid.UUID, status: JobStatus) -> None:
        job.status = status

    repo.update_status.side_effect = update_status
    files = MagicMock()
    files.create_temp_dir.return_value = tmp_path
    files.download_file.return_value = tmp_path / "voice.ogg"
    speech = MagicMock()
    speech.prepare_chunks.return_value = [AudioChunk(tmp_path / "speech.wav", 30)]
    client = MagicMock()
    client.transcribe.return_value = "Hello, yarın görüşürüz."
    delivery = MagicMock()
    queue = MagicMock()
    client_factory = MagicMock(return_value=client)
    monkeypatch.setattr(tasks, "JobRepository", lambda: repo)
    monkeypatch.setattr(tasks, "TelegramFileService", lambda: files)
    monkeypatch.setattr(tasks, "SpeechAudioService", lambda: speech)
    monkeypatch.setattr(tasks, "UstaGPTClient", client_factory)
    monkeypatch.setattr(tasks, "TranscriptDeliveryService", lambda: delivery)
    monkeypatch.setattr(tasks, "create_queue", lambda: queue)
    return SimpleNamespace(
        job=job,
        repo=repo,
        files=files,
        speech=speech,
        client=client,
        client_factory=client_factory,
        delivery=delivery,
        queue=queue,
    )


def test_silence_never_calls_transcription_api(worker_context: SimpleNamespace) -> None:
    ctx = worker_context
    ctx.speech.prepare_chunks.side_effect = NoSpeechDetectedError("No speech")
    tasks.process_transcription_job(str(ctx.job.id))
    ctx.client_factory.assert_not_called()
    ctx.delivery.deliver_transcript.assert_not_called()
    assert ctx.job.status == JobStatus.CANCELLED
    assert "konuşma algılanamadı" in ctx.delivery.edit_status.call_args.args[2]
    ctx.files.cleanup_temp_dir.assert_called_once()
    ctx.repo.close.assert_called_once()


def test_repetitive_success_response_tries_next_model(
    worker_context: SimpleNamespace,
) -> None:
    ctx = worker_context
    ctx.client.transcribe.side_effect = ["teşekkür ederim " * 30, "Hello world."]
    tasks.process_transcription_job(str(ctx.job.id))
    assert [call.kwargs["model"] for call in ctx.client.transcribe.call_args_list] == [
        "gpt-4o-transcribe",
        "gpt-4o-mini-transcribe",
    ]
    assert (
        ctx.delivery.deliver_transcript.call_args.kwargs["transcript"] == "Hello world."
    )
    assert ctx.job.status == JobStatus.SUCCEEDED


def test_never_delivers_rejected_output_when_all_models_fail(
    worker_context: SimpleNamespace,
) -> None:
    ctx = worker_context
    ctx.client.transcribe.return_value = "teşekkür ederim " * 30
    tasks.process_transcription_job(str(ctx.job.id))
    assert ctx.client.transcribe.call_count == 3
    assert ctx.job.status == JobStatus.FAILED
    ctx.delivery.deliver_transcript.assert_not_called()


def test_whisper_is_tried_after_three_rejected_models(
    worker_context: SimpleNamespace,
) -> None:
    ctx = worker_context
    ctx.job.model_chain = default_model_chain()
    ctx.client.transcribe.side_effect = ["teşekkür ederim " * 30] * 3 + ["Hello world."]
    tasks.process_transcription_job(str(ctx.job.id))
    assert [call.kwargs["model"] for call in ctx.client.transcribe.call_args_list] == [
        "gemini-3.8-flash",
        "gpt-4o-transcribe",
        "gpt-4o-mini-transcribe",
        "whisper-1",
    ]
    assert ctx.delivery.deliver_transcript.call_args.kwargs["model"] == "whisper-1"
    assert (
        ctx.delivery.deliver_transcript.call_args.kwargs["transcript"] == "Hello world."
    )
    assert ctx.job.status == JobStatus.SUCCEEDED


def test_temporary_error_schedules_next_model_with_timedelta(
    worker_context: SimpleNamespace,
) -> None:
    ctx = worker_context
    ctx.client.transcribe.side_effect = UstaGPTTemporaryError("HTTP 429")
    tasks.process_transcription_job(str(ctx.job.id))
    args = ctx.queue.enqueue_in.call_args.args
    assert args == (
        timedelta(seconds=30),
        "app.workers.tasks.process_transcription_job",
        str(ctx.job.id),
        1,
    )
    assert ctx.job.status == JobStatus.RETRY_WAIT
    ctx.delivery.deliver_transcript.assert_not_called()


def test_delayed_retry_resumes_at_next_model(worker_context: SimpleNamespace) -> None:
    ctx = worker_context
    tasks.process_transcription_job(str(ctx.job.id), model_index=1)
    ctx.repo.set_current_attempt.assert_called_once_with(ctx.job.id, 2)
    assert ctx.client.transcribe.call_args.kwargs["model"] == "gpt-4o-mini-transcribe"
    assert ctx.job.status == JobStatus.SUCCEEDED


def test_auto_language_is_omitted_from_api_call(
    worker_context: SimpleNamespace,
) -> None:
    ctx = worker_context
    tasks.process_transcription_job(str(ctx.job.id))
    assert ctx.client.transcribe.call_args.kwargs["language"] is None


def test_fallback_restarts_all_chunks_without_mixing_rejected_output(
    worker_context: SimpleNamespace,
) -> None:
    ctx = worker_context
    ctx.speech.prepare_chunks.return_value = [
        AudioChunk(Path("first.wav"), 30),
        AudioChunk(Path("second.wav"), 30),
    ]
    ctx.client.transcribe.side_effect = [
        "Discard this first model result.",
        "merhaba " * 40,
        "First accepted part.",
        "Second accepted part.",
    ]
    tasks.process_transcription_job(str(ctx.job.id))
    text = ctx.delivery.deliver_transcript.call_args.kwargs["transcript"]
    assert text == "First accepted part.\nSecond accepted part."
    assert ctx.job.status == JobStatus.SUCCEEDED


def test_delivery_failure_is_not_marked_successful(
    worker_context: SimpleNamespace,
) -> None:
    ctx = worker_context
    ctx.delivery.deliver_transcript.side_effect = TelegramDeliveryError("HTTP 400")
    tasks.process_transcription_job(str(ctx.job.id))
    assert ctx.job.status == JobStatus.FAILED
    statuses = [call.args[1] for call in ctx.repo.update_status.call_args_list]
    assert JobStatus.SUCCEEDED not in statuses


def test_completed_job_is_not_transcribed_again(
    worker_context: SimpleNamespace,
) -> None:
    ctx = worker_context
    ctx.job.status = JobStatus.SUCCEEDED
    tasks.process_transcription_job(str(ctx.job.id))
    ctx.client_factory.assert_not_called()
    ctx.files.download_file.assert_not_called()
    ctx.repo.close.assert_called_once()
