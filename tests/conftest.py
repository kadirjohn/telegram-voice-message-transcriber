from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio

from app.config import Settings, get_settings


@pytest.fixture(scope="session")
def settings() -> Settings:
    """Return application settings (reads from environment / .env)."""
    return get_settings()


@pytest_asyncio.fixture
async def _dummy() -> AsyncGenerator[None, None]:
    """Placeholder fixture for future async test setup."""
    yield
