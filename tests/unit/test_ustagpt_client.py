from __future__ import annotations

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
        assert "API key" not in result  # message is included but safe
        assert "missing_api_key" in result
