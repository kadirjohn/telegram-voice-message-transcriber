from __future__ import annotations

import base64
import json
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
from app.services.ustagpt_client import UstaGPTClient


class TestUstaGPTClient:
    def _make_client(self) -> UstaGPTClient:
        with patch("app.services.ustagpt_client.get_settings") as mock_settings:
            settings = MagicMock()
            settings.USTAGPT_BASE_URL = "https://api.ustagpt.com.tr"
            settings.USTAGPT_API_KEY = "test-key"
            settings.TELEGRAM_BOT_TOKEN = "test:token"
            settings.USTAGPT_RESPONSE_FORMAT = "text"
            settings.USTAGPT_CONNECT_TIMEOUT_SECONDS = 10
            settings.USTAGPT_READ_TIMEOUT_SECONDS = 120
            mock_settings.return_value = settings
            return UstaGPTClient()

    def test_extract_transcript_json(self) -> None:
        client = self._make_client()
        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        response.headers = {"content-type": "application/json"}
        response.json.return_value = {"text": "merhaba dünya"}

        result = client._extract_transcript(response)
        assert result == "merhaba dünya"

    def test_extract_transcript_plain_text(self) -> None:
        client = self._make_client()
        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        response.headers = {"content-type": "text/plain"}
        response.text = "merhaba dünya"

        result = client._extract_transcript(response)
        assert result == "merhaba dünya"

    def test_extract_transcript_empty_json(self) -> None:
        client = self._make_client()
        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        response.headers = {"content-type": "application/json"}
        response.json.return_value = {}

        result = client._extract_transcript(response)
        assert result == ""

    def test_handle_response_empty_transcript_raises(self) -> None:
        client = self._make_client()
        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        response.headers = {"content-type": "text/plain"}
        response.text = "   "

        with pytest.raises(EmptyTranscriptError):
            client._handle_response(response)

    def test_handle_response_401_raises_auth_error(self) -> None:
        client = self._make_client()
        response = MagicMock(spec=httpx.Response)
        response.status_code = 401

        with pytest.raises(UstaGPTAuthError):
            client._handle_response(response)

    def test_handle_response_403_raises_auth_error(self) -> None:
        client = self._make_client()
        response = MagicMock(spec=httpx.Response)
        response.status_code = 403

        with pytest.raises(UstaGPTAuthError):
            client._handle_response(response)

    def test_handle_response_429_raises_temporary_error(self) -> None:
        client = self._make_client()
        response = MagicMock(spec=httpx.Response)
        response.status_code = 429
        response.headers = {"content-type": "text/plain"}
        response.json.side_effect = ValueError()

        with pytest.raises(UstaGPTTemporaryError):
            client._handle_response(response)

    def test_handle_response_500_raises_temporary_error(self) -> None:
        client = self._make_client()
        response = MagicMock(spec=httpx.Response)
        response.status_code = 500
        response.headers = {"content-type": "text/plain"}
        response.json.side_effect = ValueError()

        with pytest.raises(UstaGPTTemporaryError):
            client._handle_response(response)

    def test_handle_response_400_raises_permanent_error(self) -> None:
        client = self._make_client()
        response = MagicMock(spec=httpx.Response)
        response.status_code = 400
        response.headers = {"content-type": "text/plain"}
        response.json.side_effect = ValueError()

        with pytest.raises(UstaGPTPermanentError):
            client._handle_response(response)

    def test_safe_error_redacts_secrets(self) -> None:
        client = self._make_client()
        response = MagicMock(spec=httpx.Response)
        response.status_code = 401
        response.json.return_value = {
            "error": {
                "message": "Missing or invalid API key",
                "type": "client_error",
                "code": "missing_api_key",
                "status": 401,
            }
        }

        result = client._safe_error(response)
        assert "API key" not in result  # Arbitrary provider messages are omitted.
        assert "missing_api_key" in result


@pytest.mark.parametrize("payload", [{}, {"text": None}, {"error": "failure"}, []])
def test_json_without_text_is_not_delivered_as_transcript(payload: object) -> None:
    with pytest.raises(EmptyTranscriptError):
        UstaGPTClient()._handle_response(httpx.Response(200, json=payload))


def test_malformed_json_is_retryable() -> None:
    response = httpx.Response(
        200, text="not json", headers={"content-type": "application/json"}
    )
    with pytest.raises(UstaGPTTemporaryError, match="malformed JSON"):
        UstaGPTClient()._handle_response(response)


@pytest.mark.parametrize("language", [None, "tr", "en"])
@pytest.mark.parametrize(
    "extension,mime", [(".wav", "audio/wav"), (".m4a", "audio/mp4")]
)
def test_uploads_wav_and_preserves_language_choice(
    tmp_path: Path, language: str | None, extension: str, mime: str
) -> None:
    audio = tmp_path / f"speech{extension}"
    audio.write_bytes(b"test audio")
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text="Hello world")

    transport = httpx.MockTransport(respond)
    with patch(
        "app.services.ustagpt_client.httpx.Client",
        return_value=httpx.Client(transport=transport),
    ):
        result = UstaGPTClient().transcribe(audio, "gpt-4o-transcribe", language)

    assert result == "Hello world"
    body = requests[0].content
    assert f"Content-Type: {mime}".encode() in body
    assert f'filename="speech{extension}"'.encode() in body
    assert (b'name="language"' in body) is (language is not None)
    # Do not assume undocumented UstaGPT parameters are supported.
    assert b'name="prompt"' not in body


def test_network_timeout_is_retryable_and_does_not_echo_secrets(tmp_path: Path) -> None:
    audio = tmp_path / "speech.wav"
    audio.write_bytes(b"test audio")

    def timeout(request: httpx.Request) -> httpx.Response:
        msg = "test-key must not be logged"
        raise httpx.ReadTimeout(msg, request=request)

    with (
        patch(
            "app.services.ustagpt_client.httpx.Client",
            return_value=httpx.Client(transport=httpx.MockTransport(timeout)),
        ),
        pytest.raises(UstaGPTTemporaryError) as exc,
    ):
        UstaGPTClient().transcribe(audio, "gpt-4o-transcribe")

    assert "test-key" not in str(exc.value)


def test_safe_error_omits_untrusted_provider_message() -> None:
    response = httpx.Response(
        500,
        json={
            "error": {
                "code": "server_error",
                "message": "Authorization: Bearer test-key; user transcript here",
            }
        },
    )
    result = UstaGPTClient()._safe_error(response)
    assert result == "code=server_error"


@pytest.mark.parametrize(
    "model", ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-3.8-flash"]
)
@pytest.mark.parametrize("language", [None, "tr"])
def test_gemini_sends_actual_audio_using_native_protocol(
    tmp_path: Path, model: str, language: str | None
) -> None:
    audio = tmp_path / "speech.wav"
    audio.write_bytes(b"actual audio bytes")
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": "Do not deliver this reasoning.",
                                    "thought": True,
                                },
                                {"text": " Merhaba. "},
                                {"text": " Hello. "},
                            ]
                        }
                    }
                ],
            },
        )

    with patch(
        "app.services.ustagpt_client.httpx.Client",
        return_value=httpx.Client(transport=httpx.MockTransport(respond)),
    ):
        assert UstaGPTClient().transcribe(audio, model, language) == "Merhaba.\nHello."

    request = requests[0]
    assert request.url.path == f"/v1beta/models/{model}:generateContent"
    assert request.headers["x-goog-api-key"] == "test-key"
    payload = json.loads(request.content)
    parts = payload["contents"][0]["parts"]
    assert parts[1]["inlineData"]["mimeType"] == "audio/wav"
    assert base64.b64decode(parts[1]["inlineData"]["data"]) == audio.read_bytes()
    assert "Preserve the original languages" in parts[0]["text"]
    assert ("expected speech language" in parts[0]["text"]) is (language is not None)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"candidates": []},
        {"candidates": [None]},
        {"candidates": [{"content": {"parts": [{"text": "", "thought": True}]}}]},
    ],
)
def test_gemini_missing_transcript_is_rejected(payload: object) -> None:
    with pytest.raises(EmptyTranscriptError):
        UstaGPTClient()._handle_response(httpx.Response(200, json=payload), gemini=True)


def test_gemini_malformed_json_is_retryable() -> None:
    with pytest.raises(UstaGPTTemporaryError, match="malformed Gemini JSON"):
        UstaGPTClient()._handle_response(
            httpx.Response(200, text="invalid"), gemini=True
        )


def test_gemini_provider_errors_use_same_fallback_policy() -> None:
    with pytest.raises(UstaGPTTemporaryError):
        UstaGPTClient()._handle_response(
            httpx.Response(503, json={"error": {"code": "UNAVAILABLE"}}), gemini=True
        )
