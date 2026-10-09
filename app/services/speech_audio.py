from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path

import webrtcvad

from app.config import get_settings
from app.services.audio_converter import AudioConverter
from app.services.exceptions import (
    AudioConversionError,
    FileTooLargeError,
    NoSpeechDetectedError,
)

SAMPLE_RATE = 16_000
SAMPLE_WIDTH = 2
FRAME_SECONDS = 0.03
FRAME_SAMPLES = 480
FRAME_BYTES = FRAME_SAMPLES * SAMPLE_WIDTH
PADDING_FRAMES = 10  # Preserve 300 ms around speech, including quiet consonants.
MIN_SILENCE_FRAMES = 67  # Keep pauses up to about two seconds for context.


@dataclass(frozen=True)
class AudioChunk:
    path: Path
    duration_seconds: float


class SpeechAudioService:
    """Prepare bounded WAV uploads and omit regions classified as non-speech.

    WebRTC VAD is a signal-processing filter; no transcription model runs
    locally. It can still mistake some noise for speech or miss quiet speech.
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    def prepare_chunks(self, input_path: Path, output_dir: Path) -> list[AudioChunk]:
        wav_path = AudioConverter().convert_to_wav(input_path, output_dir)
        # WAV files written below have a 44-byte header. Align to VAD frames.
        max_frames = min(
            int(self._settings.AUDIO_CHUNK_SECONDS / FRAME_SECONDS),
            (self._settings.MAX_VOICE_FILE_BYTES - 44) // FRAME_BYTES,
        )
        if max_frames < 1:
            msg = "The upload size limit is too small for a PCM audio frame"
            raise FileTooLargeError(msg)

        chunks: list[AudioChunk] = []
        with wave.open(str(wav_path), "rb") as source:
            if (
                source.getnchannels() != 1
                or source.getsampwidth() != SAMPLE_WIDTH
                or source.getframerate() != SAMPLE_RATE
                or source.getcomptype() != "NONE"
            ):
                msg = "Expected mono 16 kHz, 16-bit PCM audio"
                raise AudioConversionError(msg)

            duration = source.getnframes() / SAMPLE_RATE
            if duration > self._settings.MAX_VOICE_DURATION_SECONDS:
                msg = "Decoded audio exceeds the configured duration limit"
                raise AudioConversionError(msg)

            while source.tell() < source.getnframes():
                start = source.tell()
                pcm = source.readframes(max_frames * FRAME_SAMPLES)
                voiced = self._detect_speech(pcm)

                # Prefer a pause near the end of a block to a cut through a word.
                if source.tell() < source.getnframes():
                    cut_frame = self._pause_boundary(voiced)
                    if cut_frame is not None:
                        pcm = pcm[: cut_frame * FRAME_BYTES]
                        voiced = voiced[:cut_frame]
                        source.setpos(start + cut_frame * FRAME_SAMPLES)

                speech_seconds = sum(voiced) * FRAME_SECONDS
                if speech_seconds < self._settings.AUDIO_MIN_SPEECH_SECONDS:
                    continue

                ranges = self._speech_ranges(voiced)
                speech_pcm = b"".join(
                    pcm[first * FRAME_BYTES : last * FRAME_BYTES]
                    for first, last in ranges
                )
                chunk_path = output_dir / f"speech-{len(chunks):04d}.wav"
                with wave.open(str(chunk_path), "wb") as chunk:
                    chunk.setnchannels(1)
                    chunk.setsampwidth(SAMPLE_WIDTH)
                    chunk.setframerate(SAMPLE_RATE)
                    chunk.writeframes(speech_pcm)
                chunks.append(
                    AudioChunk(
                        path=chunk_path,
                        duration_seconds=len(speech_pcm) / (SAMPLE_RATE * SAMPLE_WIDTH),
                    )
                )

        if not chunks:
            msg = "No sufficient speech was detected in the recording"
            raise NoSpeechDetectedError(msg)
        return chunks

    def _detect_speech(self, pcm: bytes) -> list[bool]:
        detector = webrtcvad.Vad(self._settings.AUDIO_VAD_MODE)
        return [
            detector.is_speech(
                pcm[offset : offset + FRAME_BYTES].ljust(FRAME_BYTES, b"\x00"),
                SAMPLE_RATE,
            )
            for offset in range(0, len(pcm), FRAME_BYTES)
        ]

    @staticmethod
    def _pause_boundary(voiced: list[bool]) -> int | None:
        """Find a 210 ms pause within the final three seconds of a block."""
        run = 0
        boundary = None
        for index in range(max(1, len(voiced) - 100), len(voiced)):
            run = 0 if voiced[index] else run + 1
            if run == 7:
                boundary = index - run + 1
        return boundary

    @staticmethod
    def _speech_ranges(voiced: list[bool]) -> list[tuple[int, int]]:
        """Pad speech and keep short pauses; discard longer non-speech gaps."""
        ranges: list[tuple[int, int]] = []
        previous_speech = -MIN_SILENCE_FRAMES
        for index, is_speech in enumerate(voiced):
            if not is_speech:
                continue
            first = max(0, index - PADDING_FRAMES)
            last = min(len(voiced), index + PADDING_FRAMES + 1)
            if ranges and index - previous_speech <= MIN_SILENCE_FRAMES:
                ranges[-1] = (ranges[-1][0], last)
            else:
                ranges.append((first, last))
            previous_speech = index
        return ranges
