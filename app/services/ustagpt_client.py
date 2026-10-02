from __future__ import annotations

import base64
import re
from pathlib import Path

import httpx

from app.config import get_settings
from app.services.exceptions import (
    EmptyTranscriptError,
    UstaGPTAuthError,
    UstaGPTPermanentError,
    UstaGPTTemporaryError,
)
from app.services.model_chain import (
    MAX_CHAT_AUDIO_BASE64_BYTES,
    uses_chat_endpoint,
)

# HTTP status codes that should stop the entire model chain
AUTH_STATUSES = frozenset({401, 403})

# HTTP status codes that are retryable with a different model
RETRYABLE_STATUSES = frozenset({408, 429, 500, 502, 503, 504})

# HTTP status codes that are usually permanent regardless of model
PERMANENT_STATUSES = frozenset({400, 413, 415, 422})

# Transcribe, do not translate: the recording may be in any language and must be
# written in the language actually spoken. Asking for a specific output language
# makes the model translate instead, which is wrong for a transcription bot.
_TRANSCRIBE_PROMPT = (
    "Bu ses kaydını birebir yazıya dök. Konuşma hangi dildeyse o dilde yaz; "
    "çeviri yapma, dil değiştirme. Sadece metni yaz, başka hiçbir şey yazma."
)

# Gemini often wraps the answer in a preamble or quotes even when asked not to.
_PREAMBLE_RE = re.compile(
    r"^\s*(?:"
    r"ses (?:kaydının|kaydinin)\s+d[öo]k[üu]m[üu]\s+şu\s+şekildedir\s*:?\.?|"
    r"işte\s+(?:d[öo]k[üu]m|çeviri|transkripsiyon)\s*:?|"
    r"d[öo]k[üu]m\s*:?|"
    r"çeviri\s*:?|"
    r"transkript\s*:?|"
    r"transcription\s*:?"
    r")\s*",
    re.IGNORECASE,
)


def _clean_transcript(text: str) -> str:
    """Strip the wrappers chat models add around an otherwise clean answer."""
    cleaned = text.strip()
    previous = None
    while cleaned != previous:
        previous = cleaned
        cleaned = _PREAMBLE_RE.sub("", cleaned).strip()

    # Models often quote the whole answer; only unwrap when both quotes match.
    pairs = (('"', '"'), ("“", "”"), ("'", "'"))
    for opening, closing in pairs:
        if len(cleaned) > 2 and cleaned.startswith(opening) and cleaned.endswith(
            closing
        ):
            cleaned = cleaned[1:-1].strip()
            break

    return cleaned


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

        Dispatches on the model: Gemini-class models only accept audio through
        /v1/chat/completions, everything else through /v1/audio/transcriptions.

        Args:
            audio_path: Path to the MP3 file to transcribe.
            model: One of the supported model IDs.
            language: ISO 639-1 code or None for auto-detection.

        Returns:
            The transcribed text.

        Raises:
            UstaGPTAuthError: API key is invalid or missing.
            UstaGPTTemporaryError: Temporary server error.
            UstaGPTPermanentError: Request error that won't be fixed by retry.
            EmptyTranscriptError: Response was empty.
        """
        if uses_chat_endpoint(model):
            return self._transcribe_via_chat(audio_path, model)

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

    def _transcribe_via_chat(self, audio_path: Path, model: str) -> str:
        """Transcribe by sending the audio inline to /v1/chat/completions.

        Used for Gemini-class models, which perceive audio natively but reject
        the OpenAI-shaped /v1/audio/transcriptions endpoint.

        The ``language`` setting is deliberately not forwarded: these models
        detect the spoken language themselves, and naming an output language in
        the prompt makes them translate rather than transcribe.
        """
        encoded = base64.b64encode(audio_path.read_bytes()).decode("ascii")
        if len(encoded) > MAX_CHAT_AUDIO_BASE64_BYTES:
            msg = (
                "Ses kaydı chat üzerinden gönderilemeyecek kadar büyük "
                f"({len(encoded) / 1024 / 1024:.1f} MB base64, sınır "
                f"{MAX_CHAT_AUDIO_BASE64_BYTES / 1024 / 1024:.0f} MB)"
            )
            raise UstaGPTPermanentError(msg)

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _TRANSCRIBE_PROMPT},
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": encoded,
                                "format": "mp3",
                            },
                        },
                    ],
                }
            ],
            "temperature": 0,
        }

        url = f"{self._base_url}/v1/chat/completions"
        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

        return self._handle_chat_response(response)

    def _handle_chat_response(self, response: httpx.Response) -> str:
        """Classify a chat completion response and return the transcript."""
        status = response.status_code

        if status // 100 == 2:
            transcript = _clean_transcript(self._extract_chat_content(response))
            if not transcript:
                msg = "UstaGPT returned a successful response with an empty transcript"
                raise EmptyTranscriptError(msg)
            return transcript

        if status in AUTH_STATUSES:
            msg = f"UstaGPT returned HTTP {status} — API key is invalid or missing"
            raise UstaGPTAuthError(msg)

        if status in RETRYABLE_STATUSES:
            msg = f"UstaGPT returned HTTP {status}: {self._safe_error(response)}"
            raise UstaGPTTemporaryError(msg)

        msg = f"UstaGPT returned HTTP {status}: {self._safe_error(response)}"
        raise UstaGPTPermanentError(msg)

    def _extract_chat_content(self, response: httpx.Response) -> str:
        """Pull the assistant text out of a chat completion payload."""
        try:
            payload = response.json()
            choices = payload.get("choices")
            if isinstance(choices, list) and choices:
                message = choices[0].get("message") or {}
                content = message.get("content")
                if isinstance(content, str):
                    return content.strip()
        except Exception:  # noqa: BLE001 - fall back to the raw body
            pass
        return response.text.strip()

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
