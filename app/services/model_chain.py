from __future__ import annotations

from typing import TYPE_CHECKING

from app.config import get_settings

if TYPE_CHECKING:
    from app.db.models.group import Group

GEMINI_MODELS = frozenset({
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-3.8-flash",
})

SUPPORTED_MODELS = GEMINI_MODELS | frozenset({
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
