from __future__ import annotations

from app.services.model_chain import (
    CHAT_AUDIO_MODELS,
    SUPPORTED_MODELS,
    TRANSCRIPTION_ENDPOINT_MODELS,
    resolve_model_chain,
    uses_chat_endpoint,
)


class TestResolveModelChain:
    def test_default_order(self) -> None:
        chain = resolve_model_chain(
            "whisper-1",
            ["gpt-4o-mini-transcribe", "gpt-4o-transcribe"],
        )
        assert chain == [
            "whisper-1",
            "gpt-4o-mini-transcribe",
            "gpt-4o-transcribe",
        ]

    def test_removes_duplicates(self) -> None:
        chain = resolve_model_chain(
            "whisper-1",
            ["whisper-1", "gpt-4o-mini-transcribe"],
        )
        assert chain == ["whisper-1", "gpt-4o-mini-transcribe"]

    def test_skips_unsupported_models(self) -> None:
        chain = resolve_model_chain(
            "whisper-1",
            ["fake-model", "gpt-4o-mini-transcribe"],
        )
        assert chain == ["whisper-1", "gpt-4o-mini-transcribe"]

    def test_caps_chain_length(self) -> None:
        chain = resolve_model_chain(
            "whisper-1",
            [
                "gemini-3-flash-preview",
                "gpt-4o-mini-transcribe",
                "gpt-4o-transcribe",
                "extra-model",
            ],
        )
        assert len(chain) <= 4

    def test_whisper_first_then_gemini(self) -> None:
        chain = resolve_model_chain(
            "whisper-1",
            ["gemini-3-flash-preview", "gpt-4o-transcribe"],
        )
        assert chain[0] == "whisper-1"
        assert chain[1] == "gemini-3-flash-preview"

    def test_empty_fallbacks(self) -> None:
        chain = resolve_model_chain("whisper-1", [])
        assert chain == ["whisper-1"]

    def test_all_unsupported_returns_only_valid(self) -> None:
        chain = resolve_model_chain("invalid-model", ["also-invalid"])
        assert chain == []

    def test_supported_models_are_known(self) -> None:
        assert "whisper-1" in SUPPORTED_MODELS
        assert "gpt-4o-mini-transcribe" in SUPPORTED_MODELS
        assert "gpt-4o-transcribe" in SUPPORTED_MODELS
        assert "gemini-3-flash-preview" in SUPPORTED_MODELS

    def test_every_supported_model_has_a_transport(self) -> None:
        assert SUPPORTED_MODELS
        assert all(uses_chat_endpoint(m) for m in CHAT_AUDIO_MODELS)
        assert not any(
            uses_chat_endpoint(m) for m in TRANSCRIPTION_ENDPOINT_MODELS
        )

    def test_gemini_is_not_in_transport_set(self) -> None:
        assert CHAT_AUDIO_MODELS.isdisjoint(TRANSCRIPTION_ENDPOINT_MODELS)
        assert CHAT_AUDIO_MODELS | TRANSCRIPTION_ENDPOINT_MODELS == SUPPORTED_MODELS
