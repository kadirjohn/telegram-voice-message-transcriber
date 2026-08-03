from __future__ import annotations

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
