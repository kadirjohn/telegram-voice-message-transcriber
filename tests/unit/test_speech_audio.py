from __future__ import annotations

import random
import shutil
import subprocess
import wave
from array import array
from pathlib import Path

import pytest

from app.config import Settings
from app.services.audio_converter import AudioConverter
from app.services.exceptions import NoSpeechDetectedError
from app.services.speech_audio import FRAME_BYTES, SAMPLE_RATE, SpeechAudioService


def write_pcm(path: Path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(SAMPLE_RATE)
        audio.writeframes(pcm)


def read_pcm(path: Path) -> bytes:
    with wave.open(str(path), "rb") as audio:
        assert audio.getnchannels() == 1
        assert audio.getsampwidth() == 2
        assert audio.getframerate() == SAMPLE_RATE
        return audio.readframes(audio.getnframes())


@pytest.fixture
def decoded_audio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "decoded.wav"
    monkeypatch.setattr(AudioConverter, "convert_to_wav", lambda *_: path)
    return path


def test_real_vad_rejects_silence(decoded_audio: Path, tmp_path: Path) -> None:
    write_pcm(decoded_audio, b"\x00" * FRAME_BYTES * 100)
    with pytest.raises(NoSpeechDetectedError):
        SpeechAudioService().prepare_chunks(decoded_audio, tmp_path)
    assert not list(tmp_path.glob("speech-*.wav"))


def test_real_vad_rejects_stationary_background_noise(
    decoded_audio: Path,
    tmp_path: Path,
) -> None:
    rng = random.Random(42)
    noise = array("h", (rng.randrange(-500, 501) for _ in range(SAMPLE_RATE * 5)))
    write_pcm(decoded_audio, noise.tobytes())
    with pytest.raises(NoSpeechDetectedError):
        SpeechAudioService().prepare_chunks(decoded_audio, tmp_path)


def test_preserves_speech_and_padding(
    decoded_audio: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pcm = b"".join(
        index.to_bytes(2, "little") * (FRAME_BYTES // 2) for index in range(100)
    )
    write_pcm(decoded_audio, pcm)
    monkeypatch.setattr(
        SpeechAudioService,
        "_detect_speech",
        lambda *_: [False] * 30 + [True] * 20 + [False] * 50,
    )
    chunks = SpeechAudioService().prepare_chunks(decoded_audio, tmp_path)
    assert len(chunks) == 1
    assert read_pcm(chunks[0].path) == pcm[20 * FRAME_BYTES : 60 * FRAME_BYTES]
    assert chunks[0].duration_seconds == pytest.approx(1.2)


def test_removes_long_internal_non_speech_gaps(
    decoded_audio: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pcm = b"\x01\x00" * (FRAME_BYTES // 2) * 160
    write_pcm(decoded_audio, pcm)
    flags = [10 <= index < 20 or 140 <= index < 150 for index in range(160)]
    monkeypatch.setattr(SpeechAudioService, "_detect_speech", lambda *_: flags)
    chunks = SpeechAudioService().prepare_chunks(decoded_audio, tmp_path)
    expected = pcm[: 30 * FRAME_BYTES] + pcm[130 * FRAME_BYTES :]
    assert read_pcm(chunks[0].path) == expected


def test_keeps_short_internal_pauses_for_language_context(
    decoded_audio: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pcm = b"\x01\x00" * (FRAME_BYTES // 2) * 100
    write_pcm(decoded_audio, pcm)
    flags = [10 <= index < 20 or 80 <= index < 90 for index in range(100)]
    monkeypatch.setattr(SpeechAudioService, "_detect_speech", lambda *_: flags)
    chunks = SpeechAudioService().prepare_chunks(decoded_audio, tmp_path)
    assert read_pcm(chunks[0].path) == pcm


def test_long_speech_is_bounded_without_dropping_audio(
    decoded_audio: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pcm = b"\x01\x00" * (FRAME_BYTES // 2) * 2100
    write_pcm(decoded_audio, pcm)
    monkeypatch.setattr(
        SpeechAudioService,
        "_detect_speech",
        lambda _self, data: [True] * ((len(data) + FRAME_BYTES - 1) // FRAME_BYTES),
    )
    chunks = SpeechAudioService().prepare_chunks(decoded_audio, tmp_path)
    assert [chunk.duration_seconds for chunk in chunks] == [30, 30, 3]
    assert b"".join(read_pcm(chunk.path) for chunk in chunks) == pcm


def test_wav_uploads_respect_size_limit(
    decoded_audio: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
) -> None:
    settings.MAX_VOICE_FILE_BYTES = 100_000
    write_pcm(decoded_audio, b"\x01\x00" * (FRAME_BYTES // 2) * 500)
    monkeypatch.setattr(
        SpeechAudioService,
        "_detect_speech",
        lambda _self, data: [True] * ((len(data) + FRAME_BYTES - 1) // FRAME_BYTES),
    )
    chunks = SpeechAudioService().prepare_chunks(decoded_audio, tmp_path)
    assert len(chunks) > 1
    assert all(chunk.path.stat().st_size <= 100_000 for chunk in chunks)


def test_prefers_pause_near_chunk_boundary() -> None:
    assert SpeechAudioService._pause_boundary([True] * 990 + [False] * 10) == 990
    assert SpeechAudioService._pause_boundary([True] * 1000) is None


@pytest.mark.integration
@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg is required")
def test_silent_telegram_ogg_is_rejected_before_transcription(tmp_path: Path) -> None:
    audio = tmp_path / "telegram.ogg"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=mono",
            "-t",
            "2",
            "-c:a",
            "libopus",
            str(audio),
        ],
        check=True,
        capture_output=True,
        timeout=10,
    )
    with pytest.raises(NoSpeechDetectedError):
        SpeechAudioService().prepare_chunks(audio, tmp_path)


@pytest.mark.integration
@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg is required")
def test_wav_input_is_not_overwritten_during_conversion(tmp_path: Path) -> None:
    audio = tmp_path / "voice.wav"
    pcm = b"\x00" * FRAME_BYTES * 100
    write_pcm(audio, pcm)
    output = AudioConverter().convert_to_wav(audio, tmp_path)
    assert output != audio
    assert read_pcm(audio) == pcm
    assert read_pcm(output) == pcm
