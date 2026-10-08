from __future__ import annotations

import httpx

from app.config import get_settings
from app.services.exceptions import TelegramDeliveryError


class TranscriptDeliveryService:
    """Sends and edits transcript messages on Telegram."""

    def __init__(self, bot_token: str | None = None) -> None:
        settings = get_settings()
        self._bot_token = bot_token or settings.TELEGRAM_BOT_TOKEN
        self._base_url = f"https://api.telegram.org/bot{self._bot_token}"

    def edit_status(self, chat_id: int, message_id: int, text: str) -> None:
        """Edit an existing status message."""
        self._post(
            "editMessageText",
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
            },
        )

    def deliver_transcript(
        self,
        chat_id: int,
        reply_to_message_id: int,
        status_message_id: int | None,
        transcript: str,
        *,
        thread_id: int | None = None,
        model: str | None = None,
        show_footer: bool = False,
    ) -> None:
        footer = f"\n\n— {model}" if show_footer and model else ""
        chunks = self._chunk_text(transcript, 4096 - len(footer))
        for index, chunk in enumerate(chunks):
            text = chunk + (footer if index == len(chunks) - 1 else "")
            if index == 0 and status_message_id is not None:
                self.edit_status(chat_id, status_message_id, text)
            else:
                self.send_transcript(
                    chat_id, reply_to_message_id, text, thread_id=thread_id
                )

    def send_transcript(
        self,
        chat_id: int,
        reply_to_message_id: int,
        transcript: str,
        *,
        thread_id: int | None = None,
        model: str | None = None,
        show_footer: bool = False,
    ) -> None:
        """Send the transcript as a reply to the original voice message.

        Handles Telegram's 4096 character limit by splitting into chunks.
        """
        footer = ""
        if show_footer and model:
            footer = f"\n\n— {model}"

        max_len = 4096 - len(footer)
        chunks = self._chunk_text(transcript, max_len)

        for i, chunk in enumerate(chunks):
            text = chunk + (footer if i == len(chunks) - 1 else "")
            payload: dict = {
                "chat_id": chat_id,
                "reply_to_message_id": reply_to_message_id,
                "text": text,
            }
            if thread_id is not None:
                payload["message_thread_id"] = thread_id

            self._post("sendMessage", payload)

    def _post(self, method: str, payload: dict) -> None:
        try:
            with httpx.Client(timeout=10) as client:
                response = client.post(f"{self._base_url}/{method}", json=payload)
            if response.status_code != 200 or response.json().get("ok") is not True:
                msg = f"Telegram delivery failed (HTTP {response.status_code})"
                raise TelegramDeliveryError(msg)
        except (httpx.TransportError, ValueError, AttributeError) as exc:
            msg = "Telegram delivery could not be confirmed"
            raise TelegramDeliveryError(msg) from exc

    def _chunk_text(self, text: str, max_len: int) -> list[str]:
        """Split text into UTF-8-safe chunks at word boundaries."""
        if len(text) <= max_len:
            return [text]

        chunks: list[str] = []
        while text:
            if len(text) <= max_len:
                chunks.append(text)
                break

            split_at = text.rfind(" ", 0, max_len)
            if split_at == -1:
                split_at = max_len

            chunks.append(text[:split_at])
            text = text[split_at:].lstrip()

        return chunks
