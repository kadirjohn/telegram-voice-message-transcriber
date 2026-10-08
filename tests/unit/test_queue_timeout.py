from __future__ import annotations

from app.config import Settings
from app.queue import transcription_job_timeout


def test_long_recordings_allow_multiple_api_uploads() -> None:
    assert transcription_job_timeout(3, model_count=1) == 600
    assert transcription_job_timeout(3600) > 120 * 3 * 120


def test_unknown_duration_uses_configured_limit(settings: Settings) -> None:
    settings.MAX_VOICE_DURATION_SECONDS = 180
    assert transcription_job_timeout(None) == transcription_job_timeout(180)


def test_smaller_upload_limit_allows_time_for_extra_chunks(settings: Settings) -> None:
    normal = transcription_job_timeout(60)
    settings.MAX_VOICE_FILE_BYTES = 160_044
    assert transcription_job_timeout(60) > normal
