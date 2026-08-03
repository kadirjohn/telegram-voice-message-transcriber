from __future__ import annotations

from app.services.model_chain import SUPPORTED_MODELS, resolve_model_chain


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

    def test_caps_at_three(self) -> None:
        chain = resolve_model_chain(
            "whisper-1",
            ["gpt-4o-mini-transcribe", "gpt-4o-transcribe", "extra-model"],
        )
        assert len(chain) <= 3

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
        assert len(SUPPORTED_MODELS) == 3
