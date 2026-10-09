from __future__ import annotations

from typing import TYPE_CHECKING

from app.config import get_settings

if TYPE_CHECKING:
    from app.db.models.group import Group

# Models reached through POST /v1/audio/transcriptions (OpenAI-compatible).
TRANSCRIPTION_ENDPOINT_MODELS = frozenset({
    "whisper-1",
    "gpt-4o-mini-transcribe",
    "gpt-4o-transcribe",
})

# Models that perceive audio natively and are only reachable through the native
# generateContent endpoint. The gateway's OpenAI-shaped chat input_audio path
# returned unrelated text in live controls, so these must not use it.
GEMINI_MODELS = frozenset({
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-3.8-flash",
})

SUPPORTED_MODELS = GEMINI_MODELS | TRANSCRIPTION_ENDPOINT_MODELS

# Gemini streams large inline audio as one JSON body; past roughly this many
# base64 characters the provider answers HTTP 413.
MAX_CHAT_AUDIO_BASE64_BYTES = 20 * 1024 * 1024


def resolve_model_chain(
    primary: str,
    fallbacks: list[str],
) -> list[str]:
    """Resolve a deduplicated model chain from primary + fallbacks.

    Validates against SUPPORTED_MODELS, removes duplicates while preserving
    order, and caps at 4 models so a job cannot stall indefinitely.
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


def group_model_chain(group: Group | None) -> list[str]:
    """Resolve the group's saved overrides using the same policy as new jobs."""
    settings = get_settings()
    primary = (
        group.primary_model
        if group and group.primary_model
        else settings.USTAGPT_PRIMARY_MODEL
    )
    fallbacks = (
        group.fallback_models
        if group and group.fallback_models is not None
        else settings.USTAGPT_FALLBACK_MODELS_LIST
    )
    return resolve_model_chain(primary, fallbacks)
