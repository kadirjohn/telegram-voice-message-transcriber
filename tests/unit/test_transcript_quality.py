from __future__ import annotations

import pytest

from app.services.exceptions import EmptyTranscriptError, SuspiciousTranscriptError
from app.services.transcript_quality import validate_transcript


@pytest.mark.parametrize(
    "text",
    [
        "Merhaba, yarın toplantıya katılacağım.",
        "Hello, tomorrow we have a meeting. Sonrasında görüşürüz.",
        "Evet, evet, evet. Tamam.",
        "İzlediğiniz için teşekkürler. Altyazı M.K.",
        "Subscribe to the channel for more videos.",
        "Да, завтра увидимся. 明天见。",
    ],
)
def test_preserves_normal_speech_without_blacklists(text: str) -> None:
    assert validate_transcript(text, 10) == text


@pytest.mark.parametrize("phrase", ["merhaba ", "teşekkür ederim ", "bu bir deneme "])
def test_rejects_prolonged_repetition(phrase: str) -> None:
    with pytest.raises(SuspiciousTranscriptError, match="repetition"):
        validate_transcript(phrase * 30, 30)


def test_rejects_implausible_amount_of_text_for_short_audio() -> None:
    text = " ".join(f"word{index}" for index in range(100))
    with pytest.raises(SuspiciousTranscriptError, match="long"):
        validate_transcript(text, 1)


def test_rejects_empty_text() -> None:
    with pytest.raises(EmptyTranscriptError):
        validate_transcript("  ", 10)
