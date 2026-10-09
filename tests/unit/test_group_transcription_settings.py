from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.filters import CommandObject

from app.bot.handlers import models, voice
from app.config import Settings
from app.db.models.group import Group
from app.services.model_chain import group_model_chain


def test_default_chain_uses_native_gemini_then_transcription_models() -> None:
    assert group_model_chain(None) == [
        "gemini-3.8-flash",
        "gpt-4o-transcribe",
        "gpt-4o-mini-transcribe",
        "whisper-1",
    ]


def test_group_model_override_is_resolved_from_persisted_fields() -> None:
    group = Group(
        chat_id=-100,
        primary_model="whisper-1",
        fallback_models=["gpt-4o-transcribe"],
    )
    assert group_model_chain(group) == ["whisper-1", "gpt-4o-transcribe"]


def test_empty_group_fallback_list_is_respected() -> None:
    group = Group(chat_id=-100, primary_model="whisper-1", fallback_models=[])
    assert group_model_chain(group) == ["whisper-1"]


async def test_model_command_does_not_require_missing_model_chain_attribute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    group = Group(chat_id=-100)
    monkeypatch.setattr(models.group_repo, "get_by_chat_id", lambda _: group)
    message = SimpleNamespace(
        chat=SimpleNamespace(id=-100, type="supergroup"),
        answer=AsyncMock(),
    )
    await models.cmd_model(message)
    assert "gpt-4o-transcribe" in message.answer.call_args.args[0]


async def test_model_set_writes_only_mapped_group_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    group = Group(chat_id=-100)
    monkeypatch.setattr(models.group_repo, "get_by_chat_id", lambda _: group)
    commit = MagicMock()
    monkeypatch.setattr(models.group_repo._session, "commit", commit)
    message = SimpleNamespace(
        chat=SimpleNamespace(id=-100, type="supergroup"),
        answer=AsyncMock(),
    )
    await models.cmd_model_set(
        message, CommandObject(command="model_set", args="whisper-1")
    )
    assert group.primary_model == "whisper-1"
    assert not hasattr(group, "model_chain")
    commit.assert_called_once()


@pytest.mark.parametrize("language", ["auto", "tr", "en"])
async def test_new_jobs_use_group_model_and_language(
    language: str,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    group = Group(
        chat_id=-100,
        primary_model="whisper-1",
        fallback_models=[],
        language=language,
    )
    repo = MagicMock()
    repo.get_by_chat_message.return_value = None
    queue = MagicMock()
    monkeypatch.setattr(voice, "JobRepository", lambda: repo)
    monkeypatch.setattr(voice, "create_queue", lambda: queue)
    message = SimpleNamespace(
        message_id=10,
        message_thread_id=5,
        from_user=SimpleNamespace(id=123),
        voice=SimpleNamespace(
            duration=10,
            file_size=1000,
            file_id="file",
            file_unique_id="unique",
            mime_type="audio/ogg",
        ),
        reply=AsyncMock(return_value=SimpleNamespace(message_id=11)),
    )
    await voice._process_voice(message, -100, settings, group)
    assert repo.create.call_args.kwargs["model_chain"] == ["whisper-1"]
    assert repo.create.call_args.kwargs["language"] == language
    assert repo.create.call_args.kwargs["source_thread_id"] == 5


async def test_private_chat_keeps_auto_language(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = MagicMock()
    repo.get_by_chat_message.return_value = None
    monkeypatch.setattr(voice, "JobRepository", lambda: repo)
    monkeypatch.setattr(voice, "create_queue", MagicMock())
    message = SimpleNamespace(
        message_id=10,
        message_thread_id=None,
        from_user=SimpleNamespace(id=123),
        voice=SimpleNamespace(
            duration=10,
            file_size=1000,
            file_id="file",
            file_unique_id="unique",
            mime_type="audio/ogg",
        ),
        reply=AsyncMock(return_value=SimpleNamespace(message_id=11)),
    )
    await voice._process_voice(message, 123, settings)
    assert repo.create.call_args.kwargs["language"] == "auto"
