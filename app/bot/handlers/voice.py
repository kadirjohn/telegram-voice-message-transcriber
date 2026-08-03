from __future__ import annotations

from aiogram import Router
from aiogram.types import Message, Voice

from app.config import get_settings
from app.db.repositories.group_repository import GroupRepository
from app.db.repositories.job_repository import JobRepository
from app.logging import get_logger
from app.queue import create_queue
from app.services.model_chain import default_model_chain

router = Router(name="voice")
logger = get_logger(__name__)


@router.message(lambda msg: msg.voice is not None)
async def on_voice_message(message: Message) -> None:
    """Handle incoming voice messages in approved groups."""
    chat = message.chat
    if chat.type not in ("group", "supergroup"):
        return

    settings = get_settings()
    group_repo = GroupRepository()

    # 1. Check group is approved
    if not group_repo.is_approved(chat.id):
        logger.debug("voice_skipped_group_not_approved", chat_id=chat.id)
        return

    voice: Voice | None = message.voice
    if voice is None:
        return

    # 2. Validate duration
    max_duration = settings.MAX_VOICE_DURATION_SECONDS
    if voice.duration is not None and voice.duration > max_duration:
        await message.reply(
            f"⏱ Sesli mesaj çok uzun. Maksimum {max_duration} saniye."
        )
        return

    # 3. Validate file size
    max_size = settings.MAX_VOICE_FILE_BYTES
    if voice.file_size is not None and voice.file_size > max_size:
        await message.reply(
            f"📦 Sesli mesaj çok büyük. Maksimum {max_size // 1024 // 1024} MB."
        )
        return

    # 4. Check for duplicate
    job_repo = JobRepository()
    existing = job_repo.get_by_chat_message(chat.id, message.message_id)
    if existing is not None:
        logger.debug(
            "voice_duplicate_skipped",
            chat_id=chat.id,
            message_id=message.message_id,
            job_id=str(existing.id),
        )
        return

    # 5. Create job in database
    model_chain = default_model_chain()
    job = job_repo.create(
        chat_id=chat.id,
        source_message_id=message.message_id,
        source_thread_id=message.message_thread_id,
        sender_telegram_id=message.from_user.id if message.from_user else 0,
        telegram_file_id=voice.file_id,
        telegram_file_unique_id=voice.file_unique_id,
        duration_seconds=voice.duration,
        file_size=voice.file_size,
        mime_type=voice.mime_type,
        language=settings.USTAGPT_LANGUAGE,
        model_chain=model_chain,
    )

    # 6. Send status reply
    status_msg = await message.reply("⏳ Sesli mesaj sıraya alındı.")
    job_repo.set_status_message_id(job.id, status_msg.message_id)

    # 7. Enqueue RQ job with deterministic ID
    queue = create_queue()
    queue.enqueue(
        "app.workers.tasks.process_transcription_job",
        str(job.id),
        job_id=f"tg:{chat.id}:{message.message_id}",
        job_timeout=600,
        result_ttl=0,
    )

    logger.info(
        "voice_job_created",
        job_id=str(job.id),
        chat_id=chat.id,
        message_id=message.message_id,
        duration=voice.duration,
        model_chain=model_chain,
    )
