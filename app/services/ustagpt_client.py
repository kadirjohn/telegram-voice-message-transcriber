from __future__ import annotations

from pathlib import Path

import httpx

from app.config import get_settings
from app.services.exceptions import (
    EmptyTranscriptError,
    UstaGPTAuthError,
    UstaGPTPermanentError,
    UstaGPTTemporaryError,
)

# HTTP status codes that should stop the entire model chain
AUTH_STATUSES = frozenset({401, 403})

# HTTP status codes that are retryable with a different model
RETRYABLE_STATUSES = frozenset({408, 429, 500, 502, 503, 504})

# HTTP status codes that are usually permanent regardless of model
PERMANENT_STATUSES = frozenset({400, 413, 415, 422})


class UstaGPTClient:
    """Client for the UstaGPT audio transcription API."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._base_url = self._settings.USTAGPT_BASE_URL.rstrip("/")
        self._api_key = self._settings.USTAGPT_API_KEY
        self._timeout = httpx.Timeout(
            connect=self._settings.USTAGPT_CONNECT_TIMEOUT_SECONDS,
            read=self._settings.USTAGPT_READ_TIMEOUT_SECONDS,
            write=self._settings.USTAGPT_READ_TIMEOUT_SECONDS,
            pool=10.0,
        )

    def transcribe(
        self,
        audio_path: Path,
        model: str,
        language: str | None = None,
    ) -> str:
        """Send an audio file to UstaGPT and return the transcript text.

        Args:
            audio_path: Path to the MP3 file to transcribe.
            model: One of the supported model IDs.
            language: ISO 639-1 code or None for auto-detection.

        Returns:
            The transcribed text.

        Raises:
            UstaGPTAuthError: API key is invalid or missing.
            UstaGPTRateLimitError: Rate limited.
            UstaGPTTemporaryError: Temporary server error.
            UstaGPTPermanentError: Request error that won't be fixed by retry.
            EmptyTranscriptError: Response was empty.
        """
        url = f"{self._base_url}/v1/audio/transcriptions"

        data: dict[str, str] = {
            "model": model,
            "response_format": self._settings.USTAGPT_RESPONSE_FORMAT,
        }
        if language:
            data["language"] = language

        with audio_path.open("rb") as audio_file:
            files = {
                "file": (
                    audio_path.name,
                    audio_file,
                    "audio/mpeg",
                )
            }

            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    url,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    data=data,
                    files=files,
                )

        return self._handle_response(response)

    def _handle_response(self, response: httpx.Response) -> str:
        """Classify the response and return transcript or raise."""
        status = response.status_code

        if status // 100 == 2:
            transcript = self._extract_transcript(response)
            if not transcript:
                msg = "UstaGPT returned a successful response with an empty transcript"
                raise EmptyTranscriptError(msg)
            return transcript

        if status in AUTH_STATUSES:
            msg = f"UstaGPT returned HTTP {status} — API key is invalid or missing"
            raise UstaGPTAuthError(msg)

        if status in RETRYABLE_STATUSES:
            error_info = self._safe_error(response)
            msg = f"UstaGPT returned HTTP {status}: {error_info}"
            raise UstaGPTTemporaryError(msg)

        if status in PERMANENT_STATUSES:
            error_info = self._safe_error(response)
            msg = f"UstaGPT returned HTTP {status}: {error_info}"
            raise UstaGPTPermanentError(msg)

        error_info = self._safe_error(response)
        msg = f"UstaGPT returned HTTP {status}: {error_info}"
        raise UstaGPTTemporaryError(msg)

    def _extract_transcript(self, response: httpx.Response) -> str:
        """Extract transcript text from a 2xx response."""
        content_type = response.headers.get("content-type", "").lower()

        if "application/json" in content_type:
            payload = response.json()
            if isinstance(payload, dict):
                text = payload.get("text")
                if isinstance(text, str):
                    return text.strip()
        return response.text.strip()

    def _safe_error(self, response: httpx.Response) -> str:
        """Extract a safe error message without exposing secrets."""
        try:
            payload = response.json()
            error = payload.get("error", {})
            if isinstance(error, dict):
                parts = []
                for key in ("type", "code", "status", "message"):
                    val = error.get(key)
                    if val is not None:
                        parts.append(f"{key}={val}")
                if parts:
                    return " | ".join(parts)
        except Exception:
            pass
        return f"HTTP {response.status_code}"
