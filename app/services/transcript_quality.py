from __future__ import annotations

import math
import re

from app.services.exceptions import EmptyTranscriptError, SuspiciousTranscriptError


def validate_transcript(text: str, duration_seconds: float) -> str:
    """Reject obvious failure patterns, without rewriting what was recognized.

    This is a conservative heuristic, not a semantic check against the audio.
    Short repeated words and ordinary closing phrases remain valid speech.
    """
    text = text.strip()
    if not text:
        msg = "The transcription was empty"
        raise EmptyTranscriptError(msg)

    words = re.findall(r"\w+", text.casefold())
    # Allow fast speech and a generous allowance for very short utterances.
    if len(words) > math.ceil(duration_seconds * 7) + 12:
        msg = "The transcript is implausibly long for the audio segment"
        raise SuspiciousTranscriptError(msg)

    # Detect long loops with periods of up to eight words in linear time.
    for period in range(1, min(8, len(words) // 6) + 1):
        run = 0
        for index in range(period, len(words)):
            run = run + 1 if words[index] == words[index - period] else 0
            if run >= period * 5 and run + period >= 24:
                msg = "The transcript contains a prolonged repetition loop"
                raise SuspiciousTranscriptError(msg)

    return text
