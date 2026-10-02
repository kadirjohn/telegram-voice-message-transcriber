from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.services.exceptions import (
    EmptyTranscriptError,
    UstaGPTAuthError,
    UstaGPTPermanentError,
    UstaGPTTemporaryError,
)
from app.services.model_chain import (
    MAX_CHAT_AUDIO_BASE64_BYTES,
    resolve_model_chain,
    uses_chat_endpoint,
)
from app.services.ustagpt_client import UstaGPTClient, _clean_transcript


@pytest.fixture
def client() -> UstaGPTClient:
    with patch("app.services.ustagpt_client.get_settings") as mock_settings:
        settings = MagicMock()
        settings.USTAGPT_BASE_URL = "https://api.ustagpt.com.tr"
        settings.USTAGPT_API_KEY = "test-key"
        settings.USTAGPT_RESPONSE_FORMAT = "json"
        settings.USTAGPT_CONNECT_TIMEOUT_SECONDS = 10
        settings.USTAGPT_READ_TIMEOUT_SECONDS = 120
        mock_settings.return_value = settings
        return UstaGPTClient()


@pytest.fixture
def audio(tmp_path: Path) -> Path:
    p = tmp_path / "voice.mp3"
    p.write_bytes(b"ID3fake-mp3-bytes")
    return p


def _chat_response(status: int, content: str | None = None) -> MagicMock:
    r = MagicMock(spec=httpx.Response)
    r.status_code = status
    r.text = content or ""
    r.headers = {"content-type": "application/json"}
    if status // 100 == 2:
        r.json.return_value = {
            "choices": [{"message": {"content": content or ""}}]
        }
    else:
        r.json.return_value = {
            "error": {"message": "boom", "type": "api_error", "code": "x"}
        }
    return r


class TestTransportSelection:
    def test_gemini_models_use_chat_endpoint(self) -> None:
        assert uses_chat_endpoint("gemini-3-flash-preview")
        assert uses_chat_endpoint("gemini-2.5-pro")

    def test_openai_models_use_transcription_endpoint(self) -> None:
        assert not uses_chat_endpoint("whisper-1")
        assert not uses_chat_endpoint("gpt-4o-transcribe")


class TestChatTranscription:
    @staticmethod
    def _patched_post(payload: dict | None = None, status: int = 200) -> object:
        """Patch httpx.Client.post so the real client is still constructed."""
        if status // 100 == 2:
            response = httpx.Response(
                status,
                json={"choices": [{"message": {"content": payload or ""}}]},
            )
        else:
            response = httpx.Response(status, json={"error": {"message": "boom"}})
        return patch.object(httpx.Client, "post", return_value=response)

    def test_sends_inline_base64_audio(
        self, client: UstaGPTClient, audio: Path
    ) -> None:
        with self._patched_post("Merhaba") as mock_post:
            result = client.transcribe(audio_path=audio, model="gemini-3-flash-preview")

        assert result == "Merhaba"
        assert mock_post.call_args.args[0].endswith("/v1/chat/completions")
        body = mock_post.call_args.kwargs["json"]
        part = body["messages"][0]["content"][1]
        assert part["type"] == "input_audio"
        assert part["input_audio"]["format"] == "mp3"
        assert base64.b64decode(part["input_audio"]["data"]) == audio.read_bytes()
        assert body["temperature"] == 0

    def test_transcription_endpoint_used_for_whisper(
        self, client: UstaGPTClient, audio: Path
    ) -> None:
        response = httpx.Response(200, json={"text": "Merhaba"})
        with patch.object(httpx.Client, "post", return_value=response) as mock_post:
            result = client.transcribe(audio_path=audio, model="whisper-1")

        assert result == "Merhaba"
        assert mock_post.call_args.args[0].endswith("/v1/audio/transcriptions")

    def test_strips_preamble_and_quotes(
        self, client: UstaGPTClient, audio: Path
    ) -> None:
        noisy = 'Ses kaydının dökümü şu şekildedir:\n\n"Gökhan bir kere."'
        with self._patched_post(noisy):
            result = client.transcribe(audio_path=audio, model="gemini-3-flash-preview")
        assert result == "Gökhan bir kere."

    def test_empty_completion_raises(self, client: UstaGPTClient, audio: Path) -> None:
        with self._patched_post("  "), pytest.raises(EmptyTranscriptError):
            client.transcribe(audio_path=audio, model="gemini-3-flash-preview")

    def test_auth_error_stops_chain(self, client: UstaGPTClient, audio: Path) -> None:
        with self._patched_post(status=401), pytest.raises(UstaGPTAuthError):
            client.transcribe(audio_path=audio, model="gemini-3-flash-preview")

    def test_502_is_retryable(self, client: UstaGPTClient, audio: Path) -> None:
        with self._patched_post(status=502), pytest.raises(UstaGPTTemporaryError):
            client.transcribe(audio_path=audio, model="gemini-3-flash-preview")

    def test_413_is_permanent(self, client: UstaGPTClient, audio: Path) -> None:
        with self._patched_post(status=413), pytest.raises(UstaGPTPermanentError):
            client.transcribe(audio_path=audio, model="gemini-3-flash-preview")

    def test_oversized_audio_rejected_before_sending(
        self, client: UstaGPTClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "app.services.ustagpt_client.MAX_CHAT_AUDIO_BASE64_BYTES", 4
        )
        big = MagicMock(spec=Path)
        big.read_bytes.return_value = b"x" * 100
        with patch.object(httpx.Client, "post") as mock_post:
            with pytest.raises(UstaGPTPermanentError, match="büyük"):
                client.transcribe(audio_path=big, model="gemini-3-flash-preview")
            mock_post.assert_not_called()

    def test_size_limit_constant_is_sane(self) -> None:
        assert MAX_CHAT_AUDIO_BASE64_BYTES >= 5 * 1024 * 1024
        assert MAX_CHAT_AUDIO_BASE64_BYTES <= 30 * 1024 * 1024


class TestCleanTranscript:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Merhaba dünya", "Merhaba dünya"),
            ("  Merhaba  ", "Merhaba"),
            ('"Merhaba"', "Merhaba"),
            ("“Merhaba”", "Merhaba"),
            ("Ses kaydının dökümü şu şekildedir:\n\n\"Merhaba\"", "Merhaba"),
            ("İşte döküm: Merhaba", "Merhaba"),
            ("çeviri: Merhaba", "Merhaba"),
            ("", ""),
        ],
    )
    def test_strips_wrappers(self, raw: str, expected: str) -> None:
        assert _clean_transcript(raw) == expected

    def test_keeps_inner_quotes(self) -> None:
        assert _clean_transcript('Bana "merhaba" dedi') == 'Bana "merhaba" dedi'


class TestModelChain:
    def test_whisper_first_then_gemini(self) -> None:
        chain = resolve_model_chain(
            "whisper-1", ["gemini-3-flash-preview", "gpt-4o-transcribe"]
        )
        assert chain[0] == "whisper-1"
        assert chain[1] == "gemini-3-flash-preview"

    def test_gemini_kept_in_chain(self) -> None:
        chain = resolve_model_chain("whisper-1", ["gemini-3-flash-preview"])
        assert "gemini-3-flash-preview" in chain

    def test_unknown_model_dropped(self) -> None:
        assert resolve_model_chain("whisper-1", ["boyle-model-yok"]) == ["whisper-1"]

    def test_duplicates_removed(self) -> None:
        chain = resolve_model_chain(
            "whisper-1", ["whisper-1", "gemini-3-flash-preview"]
        )
        assert chain.count("whisper-1") == 1

    def test_chain_capped(self) -> None:
        chain = resolve_model_chain(
            "whisper-1",
            [
                "gemini-3-flash-preview",
                "gemini-2.5-pro",
                "gpt-4o-transcribe",
                "gpt-4o-mini-transcribe",
            ],
        )
        assert len(chain) <= 4
