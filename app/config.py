from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────
    APP_ENV: str = Field(
        default="production",
        pattern=r"^(production|staging|development)$",
    )
    LOG_LEVEL: str = Field(
        default="INFO",
        pattern=r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
    )

    # ── Telegram ─────────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = Field(min_length=1)
    OWNER_TELEGRAM_ID: int = Field(gt=0)
    ALLOW_ADMIN_PRIVATE_TRANSCRIPTION: bool = Field(default=False)

    # ── Database ─────────────────────────────────────────────────────────
    DATABASE_URL: str = Field(
        default="postgresql+psycopg2://transcriber:transcriber@postgres:5432/transcriber",
        min_length=1,
    )

    # ── Redis / Queue ─────────────────────────────────────────────────────
    REDIS_URL: str = Field(default="redis://redis:6379/0", min_length=1)
    RQ_QUEUE_NAME: str = Field(default="transcriptions", min_length=1)
    WORKER_COUNT: int = Field(default=2, ge=1, le=16)

    # ── UstaGPT ──────────────────────────────────────────────────────────
    USTAGPT_BASE_URL: str = Field(default="https://api.ustagpt.com.tr", min_length=1)
    USTAGPT_API_KEY: str = Field(min_length=1)
    USTAGPT_PRIMARY_MODEL: str = Field(default="whisper-1", min_length=1)
    USTAGPT_FALLBACK_MODELS: str = Field(
        default="gpt-4o-mini-transcribe,gpt-4o-transcribe",
        min_length=1,
    )
    USTAGPT_LANGUAGE: str = Field(default="tr", min_length=1)
    # UstaGPT's /v1/audio/transcriptions returns HTTP 502 for text, srt and vtt
    # (only json, or omitting the field, succeeds). json is the safe default;
    # _extract_transcript() parses {"text": ...} responses correctly.
    USTAGPT_RESPONSE_FORMAT: str = Field(
        default="json",
        pattern=r"^(json|text|srt|vtt)$",
    )
    USTAGPT_CONNECT_TIMEOUT_SECONDS: int = Field(default=10, ge=1, le=60)
    USTAGPT_READ_TIMEOUT_SECONDS: int = Field(default=120, ge=1, le=600)
    # Wait before retrying the next model in the chain after a retryable error.
    USTAGPT_RETRY_DELAY_SECONDS: int = Field(default=30, ge=1, le=600)

    # ── Voice / Media ────────────────────────────────────────────────────
    MAX_VOICE_FILE_BYTES: int = Field(default=20_971_520, ge=1, le=20_971_520)
    MAX_VOICE_DURATION_SECONDS: int = Field(default=3600, ge=1, le=7200)
    FFMPEG_TIMEOUT_SECONDS: int = Field(default=120, ge=10, le=600)

    # ── Transcript Storage ───────────────────────────────────────────────
    STORE_TRANSCRIPTS: bool = Field(default=True)
    TRANSCRIPT_RETENTION_HOURS: int = Field(default=24, ge=1, le=8760)
    SHOW_MODEL_FOOTER: bool = Field(default=False)

    # ── Derived ──────────────────────────────────────────────────────────
    USTAGPT_FALLBACK_MODELS_LIST: list[str] = Field(default_factory=list, init=False)

    @field_validator("USTAGPT_FALLBACK_MODELS", mode="before")
    @classmethod
    def _validate_fallback_models(cls, v: str) -> str:
        if not v.strip():
            return "gpt-4o-mini-transcribe,gpt-4o-transcribe"
        return v

    def model_post_init(self, __context: object) -> None:
        """Populate derived fields after initialisation."""
        raw = self.USTAGPT_FALLBACK_MODELS
        self.USTAGPT_FALLBACK_MODELS_LIST = [
            m.strip() for m in raw.split(",") if m.strip()
        ]

    # ── Paths ────────────────────────────────────────────────────────────
    @property
    def temp_dir(self) -> Path:
        return Path("/tmp/telegram-voice-transcriber")


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
