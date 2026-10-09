from __future__ import annotations

from aiogram import Router
from aiogram.types import Message, Voice

from app.config import Settings, get_settings
from app.db.enums import GroupStatus
from app.db.models.group import Group
from app.db.repositories.group_repository import GroupRepository
from app.db.repositories.job_repository import JobRepository
from app.logging import get_logger
from app.queue import create_queue, transcription_job_timeout
from app.services.authorization import AuthorizationService
from app.services.model_chain import group_model_chain

router = Router(name="voice")
logger = get_logger(__name__)


@router.message(lambda msg: msg.voice is not None)
async def on_voice_message(message: Message) -> None:
    """Handle incoming voice messages in approved groups or private chat."""
    chat = message.chat
    settings = get_settings()
    auth = AuthorizationService()

    # Private chat: only for owner/admin if enabled
    if chat.type == "private":
        if not settings.ALLOW_ADMIN_PRIVATE_TRANSCRIPTION:
            return
        user_id = message.from_user.id if message.from_user else 0
        if not auth.is_admin(user_id):
            return
        # Process private voice directly
        await _process_voice(message, chat.id, settings)
        return

    # Group chat: must be approved
    if chat.type not in ("group", "supergroup"):
        return

    group_repo = GroupRepository()
    group = group_repo.get_by_chat_id(chat.id)
    if group is None or group.status != GroupStatus.APPROVED or not group.is_enabled:
        logger.debug("voice_skipped_group_not_approved", chat_id=chat.id)
        return

    await _process_voice(message, chat.id, settings, group)


async def _process_voice(
    message: Message, chat_id: int, settings: Settings, group: Group | None = None
) -> None:
    """Validate, create job, and enqueue for transcription."""
    voice: Voice | None = message.voice
    if voice is None:
        return

    max_dur = settings.MAX_VOICE_DURATION_SECONDS
    if voice.duration is not None and voice.duration > max_dur:
        await message.reply(f"⏱ Sesli mesaj çok uzun. Maksimum {max_dur} saniye.")
        return

    max_size = settings.MAX_VOICE_FILE_BYTES
    if voice.file_size is not None and voice.file_size > max_size:
        max_mb = max_size // 1024 // 1024
        await message.reply(f"📦 Sesli mesaj çok büyük. Maksimum {max_mb} MB.")
        return

    # Check for duplicate
    job_repo = JobRepository()
    existing = job_repo.get_by_chat_message(chat_id, message.message_id)
    if existing is not None:
        logger.debug(
            "voice_duplicate_skipped",
            chat_id=chat_id,
            message_id=message.message_id,
            job_id=str(existing.id),
        )
        return

    # Create job
    model_chain = group_model_chain(group)
    job = job_repo.create(
        chat_id=chat_id,
        source_message_id=message.message_id,
        source_thread_id=message.message_thread_id,
        sender_telegram_id=message.from_user.id if message.from_user else 0,
        telegram_file_id=voice.file_id,
        telegram_file_unique_id=voice.file_unique_id,
        duration_seconds=voice.duration,
        file_size=voice.file_size,
        mime_type=voice.mime_type,
        language=group.language
        if group and group.language
        else settings.USTAGPT_LANGUAGE,
        model_chain=model_chain,
    )

    # Send status reply
    status_msg = await message.reply("⏳ Sesli mesaj sıraya alındı.")
    job_repo.set_status_message_id(job.id, status_msg.message_id)

    # Enqueue RQ job
    queue = create_queue()
    queue.enqueue(
        "app.workers.tasks.process_transcription_job",
        str(job.id),
        job_timeout=transcription_job_timeout(
            voice.duration, model_count=len(model_chain)
        ),
        result_ttl=0,
    )

    logger.info(
        "voice_job_created",
        job_id=str(job.id),
        chat_id=chat_id,
        message_id=message.message_id,
        duration=voice.duration,
        model_chain=model_chain,
    )
