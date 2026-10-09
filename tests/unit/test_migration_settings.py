from __future__ import annotations

from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import Settings


def test_migrations_use_application_database_url_with_encoded_password(
    settings: Settings,
) -> None:
    settings.DATABASE_URL = (
        "postgresql+psycopg2://test:p%40ss%25word@configured-db:5432/custom_db"
    )
    root = Path(__file__).resolve().parents[2]
    output = StringIO()
    config = Config(str(root / "alembic.ini"), output_buffer=output)
    config.set_main_option("script_location", str(root / "migrations"))

    command.upgrade(config, "head", sql=True)

    assert config.get_main_option("sqlalchemy.url") == settings.DATABASE_URL
    assert "CREATE TABLE transcription_jobs" in output.getvalue()
    assert "p%40ss" not in output.getvalue()
