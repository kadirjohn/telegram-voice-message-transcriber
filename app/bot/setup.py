from __future__ import annotations

from aiogram import Dispatcher
from aiogram.filters import CommandStart

from app.logging import get_logger

logger = get_logger(__name__)


async def cmd_start(message: object) -> None:
    """Handle /start command."""
    from aiogram.types import Message

    msg = message
    if not isinstance(msg, Message):
        return

    await msg.answer(
        "👋 Merhaba! Ben Sesli Mesaj Çevirici Botuyum.\n\n"
        "Bir gruba eklenip onaylandıktan sonra, o gruptaki sesli mesajları "
        "otomatik olarak yazıya çeviririm.\n\n"
        "Detaylı bilgi için /help yazabilirsiniz."
    )


async def cmd_help(message: object) -> None:
    """Handle /help command."""
    from aiogram.types import Message

    msg = message
    if not isinstance(msg, Message):
        return

    await msg.answer(
        "📖 Yardım\n\n"
        "Bu bot, onaylanmış gruplardaki sesli mesajları UstaGPT API'si "
        "kullanarak yazıya çevirir.\n\n"
        "Komutlar:\n"
        "/start — Botu başlat\n"
        "/help — Bu yardım mesajı\n"
        "/status — Bot durumu\n\n"
        "Yönetici komutları için /help_admin yazabilirsiniz."
    )


def setup_dispatcher() -> Dispatcher:
    """Create and configure the aiogram Dispatcher."""
    dp = Dispatcher()

    # Register basic handlers
    dp.message.register(cmd_start, CommandStart())
    dp.message.register(cmd_help, CommandStart(commands=["help"]))

    logger.info("dispatcher_configured")
    return dp
