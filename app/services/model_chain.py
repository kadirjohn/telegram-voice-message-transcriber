from __future__ import annotations

from app.config import get_settings

SUPPORTED_MODELS = frozenset({
    "whisper-1",
    "gpt-4o-mini-transcribe",
    "gpt-4o-transcribe",
})


def resolve_model_chain(
    primary: str,
    fallbacks: list[str],
) -> list[str]:
    """Resolve a deduplicated model chain from primary + fallbacks.

    Validates against SUPPORTED_MODELS, removes duplicates while preserving
    order, and caps at 3 models.
    """
    ordered = [primary, *fallbacks]
    result: list[str] = []

    for model in ordered:
        if model not in SUPPORTED_MODELS:
            continue
        if model not in result:
            result.append(model)

    return result[:3]


def default_model_chain() -> list[str]:
    """Return the default model chain from settings."""
    settings = get_settings()
    return resolve_model_chain(
        primary=settings.USTAGPT_PRIMARY_MODEL,
        fallbacks=settings.USTAGPT_FALLBACK_MODELS_LIST,
    )
