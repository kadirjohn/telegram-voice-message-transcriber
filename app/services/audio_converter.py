from __future__ import annotations

import subprocess
from pathlib import Path

from app.config import get_settings


class AudioConversionError(RuntimeError):
    """Raised when FFmpeg conversion fails."""


class AudioConverter:
    """Converts OGG/Opus voice messages to MP3 for UstaGPT."""

    def __init__(self) -> None:
        self._settings = get_settings()

    def convert_to_mp3(self, input_path: Path, output_dir: Path) -> Path:
        """Convert an OGG/Opus file to MP3 using FFmpeg.

        Args:
            input_path: Path to the input OGG file.
            output_dir: Directory to write the output MP3 file.

        Returns:
            Path to the converted MP3 file.

        Raises:
            AudioConversionError: If conversion fails or output is invalid.
        """
        output_path = output_dir / f"{input_path.stem}.mp3"
        timeout = self._settings.FFMPEG_TIMEOUT_SECONDS

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-y",
            "-i", str(input_path),
            "-vn",
            "-map_metadata", "-1",
            "-ac", "1",
            "-ar", "16000",
            "-c:a", "libmp3lame",
            "-b:a", "64k",
            str(output_path),
        ]

        try:
            subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            msg = (
                f"FFmpeg failed (code {exc.returncode}): "
                f"{exc.stderr.decode(errors='replace')[:200]}"
            )
            raise AudioConversionError(msg) from exc
        except subprocess.TimeoutExpired as exc:
            msg = f"FFmpeg timed out after {timeout}s"
            raise AudioConversionError(msg) from exc

        if not self._validate_output(output_path):
            msg = f"Converted file is invalid or empty: {output_path}"
            raise AudioConversionError(msg)

        return output_path

    def _validate_output(self, path: Path) -> bool:
        """Check the converted file exists, is non-empty, and has a valid duration."""
        if not path.exists():
            return False
        if path.stat().st_size == 0:
            return False

        # Check duration via ffprobe
        cmd = [
            "ffprobe",
            "-hide_banner",
            "-loglevel", "error",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            str(path),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=10, check=True)
            duration_str = result.stdout.decode().strip()
            if not duration_str:
                return False
            duration = float(duration_str)
            return duration > 0
        except (subprocess.CalledProcessError, ValueError):
            return False
