from __future__ import annotations

import uuid

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from app.bot.filters.role_filter import RoleFilter
from app.db.enums import JobStatus
from app.db.repositories.job_repository import JobRepository
from app.queue import create_queue

router = Router(name="jobs")
job_repo = JobRepository()


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    """Show bot status."""
    await message.answer(
        "✅ Bot çalışıyor.\n\n"
        "Sesli mesajları almak için botu bir gruba ekleyin "
        "ve bir yöneticinin `/approve_here` komutunu kullanmasını bekleyin."
    )


@router.message(Command("jobs_failed"), RoleFilter.admin())
async def cmd_jobs_failed(message: Message) -> None:
    """List failed jobs."""
    failed = job_repo.get_failed()
    if not failed:
        await message.answer("Hiç başarısız iş yok.")
        return

    lines = []
    for job in failed[:10]:
        short_id = str(job.id)[:8]
        lines.append(
            f"• `{short_id}` — chat {job.chat_id}, "
            f"mesaj {job.source_message_id}"
        )
    await message.answer("❌ **Başarısız İşler:**\n\n" + "\n".join(lines))


@router.message(Command("job_retry"), RoleFilter.admin())
async def cmd_job_retry(message: Message, command: CommandObject) -> None:
    """Retry a failed job. Usage: /job_retry <job_id>"""
    if not command.args:
        await message.answer(
            "Kullanım: `/job_retry <job_id>`\n"
            "İş kimliğini `/jobs_failed` ile görebilirsiniz."
        )
        return

    try:
        job_uuid = uuid.UUID(command.args.strip())
    except ValueError:
        await message.answer("Geçersiz iş kimliği.")
        return

    job = job_repo.get_by_id(job_uuid)
    if job is None:
        await message.answer("İş bulunamadı.")
        return

    if job.status != JobStatus.FAILED:
        await message.answer("Bu iş başarısız durumunda değil.")
        return

    # Reset and re-enqueue
    job.current_attempt = 0
    job.status = JobStatus.QUEUED
    job_repo._session.commit()

    queue = create_queue()
    queue.enqueue(
        "app.workers.tasks.process_transcription_job",
        str(job.id),
        job_id=f"tg-{job.chat_id}-{job.source_message_id}",
        job_timeout=600,
        result_ttl=0,
    )

    await message.answer(f"✅ İş `{str(job.id)[:8]}` yeniden kuyruğa alındı.")
