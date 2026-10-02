from __future__ import annotations

from app.config import get_settings

# Models reached through POST /v1/audio/transcriptions (OpenAI-compatible).
TRANSCRIPTION_ENDPOINT_MODELS = frozenset({
    "whisper-1",
    "gpt-4o-mini-transcribe",
    "gpt-4o-transcribe",
})

# Models that perceive audio natively but are only reachable through
# POST /v1/chat/completions with an inline base64 `input_audio` part. The
# transcription endpoint rejects these with HTTP 400.
CHAT_AUDIO_MODELS = frozenset({
    "gemini-3.8-flash",
    "gemini-3-flash-preview",
    "gemini-3.5-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
})

SUPPORTED_MODELS = TRANSCRIPTION_ENDPOINT_MODELS | CHAT_AUDIO_MODELS

# Gemini models stream large inline audio as one JSON body; past roughly this
# many base64 characters the provider answers HTTP 413.
MAX_CHAT_AUDIO_BASE64_BYTES = 20 * 1024 * 1024


def uses_chat_endpoint(model: str) -> bool:
    """Return True when the model must be called via /v1/chat/completions."""
    return model in CHAT_AUDIO_MODELS


def resolve_model_chain(
    primary: str,
    fallbacks: list[str],
) -> list[str]:
    """Resolve a deduplicated model chain from primary + fallbacks.

    Validates against SUPPORTED_MODELS and removes duplicates while preserving
    order. A single transcription-endpoint model is always kept even when
    duplicated, but the chain is capped so a job cannot stall indefinitely.
    """
    ordered = [primary, *fallbacks]
    result: list[str] = []

    for model in ordered:
        if model not in SUPPORTED_MODELS:
            continue
        if model not in result:
            result.append(model)

    return result[:4]


def default_model_chain() -> list[str]:
    """Return the default model chain from settings."""
    settings = get_settings()
    return resolve_model_chain(
        primary=settings.USTAGPT_PRIMARY_MODEL,
        fallbacks=settings.USTAGPT_FALLBACK_MODELS_LIST,
    )
