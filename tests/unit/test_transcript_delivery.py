from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from app.services.exceptions import TelegramDeliveryError
from app.services.transcript_delivery import TranscriptDeliveryService


class TestTranscriptDeliveryChunking:
    def setup_method(self) -> None:
        self.service = TranscriptDeliveryService(bot_token="test:token")

    def test_short_text_no_chunking(self) -> None:
        text = "kısa metin"
        chunks = self.service._chunk_text(text, 4096)
        assert chunks == [text]

    def test_exact_fit_no_chunking(self) -> None:
        text = "a" * 4096
        chunks = self.service._chunk_text(text, 4096)
        assert chunks == [text]

    def test_long_text_chunks_at_word_boundary(self) -> None:
        text = "kelime " * 1000  # ~7000 chars
        chunks = self.service._chunk_text(text, 100)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 100

    def test_long_text_no_spaces_forced_split(self) -> None:
        text = "a" * 5000
        chunks = self.service._chunk_text(text, 100)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 100

    def test_unicode_text_preserved(self) -> None:
        text = "ğüşıöçĞÜŞİÖÇ " * 500
        chunks = self.service._chunk_text(text, 200)
        for chunk in chunks:
            assert len(chunk) <= 200
        # Reconstruct and verify content preserved
        reconstructed = "".join(chunks).replace(" ", "")
        original = text.replace(" ", "")
        assert reconstructed == original


def test_short_transcript_edits_existing_message_without_duplicate() -> None:
    service = TranscriptDeliveryService()
    with (
        patch.object(service, "edit_status") as edit,
        patch.object(service, "send_transcript") as send,
    ):
        service.deliver_transcript(-100, 10, 11, "Merhaba")
    edit.assert_called_once_with(-100, 11, "Merhaba")
    send.assert_not_called()


def test_long_transcript_is_delivered_completely_with_thread_preserved() -> None:
    service = TranscriptDeliveryService()
    text = "a" * 5000
    with (
        patch.object(service, "edit_status") as edit,
        patch.object(service, "send_transcript") as send,
    ):
        service.deliver_transcript(-100, 10, 11, text, thread_id=5)
    first = edit.call_args.args[2]
    remaining = send.call_args.args[2]
    assert first + remaining == text
    assert len(first) <= 4096
    assert send.call_args.kwargs["thread_id"] == 5


@pytest.mark.parametrize(
    "status, payload",
    [
        (400, {"ok": False}),
        (200, {"ok": False}),
    ],
)
def test_rejected_telegram_response_raises(status: int, payload: dict) -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(status, json=payload))
    with (
        patch(
            "app.services.transcript_delivery.httpx.Client",
            return_value=httpx.Client(transport=transport),
        ),
        pytest.raises(TelegramDeliveryError),
    ):
        TranscriptDeliveryService().edit_status(-100, 11, "Merhaba")
