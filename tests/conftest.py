from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio

import app.config as config
from app.config import Settings

# Set safe settings before test modules import the database engine. Tests never
# depend on a developer's credentials, .env, or running external services.
_test_settings = Settings(
    _env_file=None,
    TELEGRAM_BOT_TOKEN="123456789:test-token",
    OWNER_TELEGRAM_ID=123456789,
    USTAGPT_API_KEY="test-key",
    DATABASE_URL="postgresql+psycopg2://test:test@127.0.0.1:1/test",
    REDIS_URL="redis://127.0.0.1:1/0",
)
config._settings = _test_settings


@pytest.fixture(autouse=True)
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Use fresh, isolated application settings for every test."""
    settings = Settings(_env_file=None, **_test_settings.model_dump())
    monkeypatch.setattr(config, "_settings", settings)
    return settings


@pytest_asyncio.fixture
async def _dummy() -> AsyncGenerator[None, None]:
    """Placeholder fixture for future async test setup."""
    yield
