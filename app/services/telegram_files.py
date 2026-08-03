from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import httpx

from app.config import get_settings


class TelegramFileService:
    """Downloads voice files from Telegram and manages temp directories."""

    def __init__(self, bot_token: str | None = None) -> None:
        settings = get_settings()
        self._bot_token = bot_token or settings.TELEGRAM_BOT_TOKEN
        self._base_url = f"https://api.telegram.org/bot{self._bot_token}"

    def create_temp_dir(self) -> Path:
        """Create a unique temporary directory for a job."""
        settings = get_settings()
        base = settings.temp_dir
        base.mkdir(parents=True, exist_ok=True)
        return Path(tempfile.mkdtemp(dir=base))

    @staticmethod
    def cleanup_temp_dir(temp_dir: Path) -> None:
        """Remove a temporary directory and all its contents."""
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)

    def get_file_path(self, file_id: str) -> str | None:
        """Resolve a Telegram file_id to a downloadable file path."""
        url = f"{self._base_url}/getFile"
        with httpx.Client(timeout=10) as client:
            response = client.post(url, json={"file_id": file_id})

        if response.status_code != 200:
            return None

        data = response.json()
        if not data.get("ok"):
            return None

        return data["result"].get("file_path")

    def download_file(self, file_id: str, dest_path: Path) -> Path:
        """Download a Telegram file to a local path. Returns the destination path."""
        file_path = self.get_file_path(file_id)
        if file_path is None:
            msg = f"Could not resolve file_id: {file_id}"
            raise FileNotFoundError(msg)

        download_url = f"https://api.telegram.org/file/bot{self._bot_token}/{file_path}"
        dest = dest_path / Path(file_path).name

        with httpx.Client(timeout=60) as client:
            response = client.get(download_url)
            response.raise_for_status()

        dest.write_bytes(response.content)
        return dest
