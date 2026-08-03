from __future__ import annotations

from aiogram import Dispatcher
from aiogram.filters import Command, CommandStart

from app.bot.handlers import admin, groups, jobs, models, voice
from app.bot.handlers import help as help_module
from app.bot.middlewares.registration import RegistrationMiddleware
from app.logging import get_logger
from app.services.authorization import AuthorizationService

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

    # Bootstrap owner on startup
    auth = AuthorizationService()
    auth.bootstrap_owner()

    # Register middlewares
    dp.message.middleware(RegistrationMiddleware())

    # Register routers (handlers)
    dp.include_router(admin.router)
    dp.include_router(groups.router)
    dp.include_router(voice.router)
    dp.include_router(models.router)
    dp.include_router(jobs.router)
    dp.include_router(help_module.router)

    # Register basic handlers
    dp.message.register(cmd_start, CommandStart())
    dp.message.register(cmd_help, Command(commands=["help"]))

    logger.info("dispatcher_configured")
    return dp
