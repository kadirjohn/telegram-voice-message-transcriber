from __future__ import annotations


class TelegramDownloadError(RuntimeError):
    """Failed to download a file from Telegram."""


class FileTooLargeError(RuntimeError):
    """The voice file exceeds the configured size limit."""


class AudioConversionError(RuntimeError):
    """FFmpeg conversion failed."""


class UstaGPTAuthError(RuntimeError):
    """UstaGPT returned 401 or 403 — API key is invalid or missing."""


class UstaGPTRateLimitError(RuntimeError):
    """UstaGPT returned 429 — rate limited."""


class UstaGPTTemporaryError(RuntimeError):
    """UstaGPT returned a retryable error (5xx, timeout, etc.)."""


class UstaGPTPermanentError(RuntimeError):
    """UstaGPT returned a non-retryable error (400, 413, 415, 422)."""


class EmptyTranscriptError(RuntimeError):
    """UstaGPT returned a successful response with an empty transcript."""


class NoSpeechDetectedError(RuntimeError):
    """The recording did not contain enough detected speech to transcribe."""


class SuspiciousTranscriptError(RuntimeError):
    """A transcript has an implausible length or severe repetition."""


class TelegramDeliveryError(RuntimeError):
    """Failed to send or edit a message on Telegram."""
