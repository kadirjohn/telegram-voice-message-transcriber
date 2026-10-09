from __future__ import annotations

from app.services.model_chain import (
    GEMINI_MODELS,
    SUPPORTED_MODELS,
    TRANSCRIPTION_ENDPOINT_MODELS,
    default_model_chain,
    resolve_model_chain,
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

    def test_caps_at_four(self) -> None:
        chain = resolve_model_chain(
            "gemini-3.8-flash",
            [
                "gpt-4o-transcribe",
                "gpt-4o-mini-transcribe",
                "whisper-1",
                "gemini-2.5-flash",
                "gemini-2.5-pro",
            ],
        )
        assert chain == [
            "gemini-3.8-flash",
            "gpt-4o-transcribe",
            "gpt-4o-mini-transcribe",
            "whisper-1",
        ]

    def test_preserves_whisper_first_server_fallback_order(self) -> None:
        assert resolve_model_chain(
            "gemini-3.8-flash",
            ["whisper-1", "gpt-4o-mini-transcribe", "gpt-4o-transcribe"],
        ) == [
            "gemini-3.8-flash",
            "whisper-1",
            "gpt-4o-mini-transcribe",
            "gpt-4o-transcribe",
        ]

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
        assert "gemini-2.5-flash" in SUPPORTED_MODELS
        assert "gemini-2.5-pro" in SUPPORTED_MODELS
        assert "gemini-3.8-flash" in SUPPORTED_MODELS
        assert len(SUPPORTED_MODELS) == 6

    def test_gemini_can_fallback_to_transcription_models(self) -> None:
        assert resolve_model_chain(
            "gemini-2.5-flash", ["gpt-4o-transcribe", "gpt-4o-mini-transcribe"]
        ) == ["gemini-2.5-flash", "gpt-4o-transcribe", "gpt-4o-mini-transcribe"]

    def test_every_supported_model_has_a_transport(self) -> None:
        assert SUPPORTED_MODELS
        assert GEMINI_MODELS.isdisjoint(TRANSCRIPTION_ENDPOINT_MODELS)
        assert GEMINI_MODELS | TRANSCRIPTION_ENDPOINT_MODELS == SUPPORTED_MODELS

    def test_default_chain_prefers_gemini_then_whisper(self) -> None:
        chain = default_model_chain()
        assert chain[0] == "gemini-3.8-flash"
        assert "whisper-1" in chain
