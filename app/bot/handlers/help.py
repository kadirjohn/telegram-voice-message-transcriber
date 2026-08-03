from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router(name="help")


@router.message(Command("help_admin"))
async def cmd_help_admin(message: Message) -> None:
    """Show admin commands."""
    await message.answer(
        "👑 **Yönetici Komutları:**\n\n"
        "**Grup Yönetimi:**\n"
        "/approve_here — Bu grubu onayla\n"
        "/revoke_here — Bu grubu iptal et\n"
        "/group_approve <chat_id> — ID ile onayla\n"
        "/group_revoke <chat_id> — ID ile iptal et\n"
        "/pending_groups — Bekleyen gruplar\n"
        "/groups — Tüm gruplar\n\n"
        "**Model Ayarları:**\n"
        "/model — Model zincirini göster\n"
        "/model_set <id> — Birincil modeli değiştir\n"
        "/fallbacks — Yedek model sırası\n"
        "/language — Dili göster\n"
        "/language_set <kod> — Dili değiştir\n\n"
        "**İş Yönetimi:**\n"
        "/jobs_failed — Başarısız işler\n"
        "/job_retry <id> — İşi yeniden dene\n\n"
        "**Sahip Komutları:**\n"
        "/admin_add <id> — Admin ekle\n"
        "/admin_remove <id> — Admin çıkar\n"
        "/admins — Admin listesi\n"
        "/fallbacks_set ... — Yedek sırasını değiştir\n"
        "/stats — İstatistikler"
    )
