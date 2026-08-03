from __future__ import annotations

import asyncio
import signal

import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.setup import setup_dispatcher
from app.config import get_settings
from app.logging import configure_logging, get_logger
from app.queue import create_redis_connection

logger: structlog.stdlib.BoundLogger = get_logger(__name__)


async def health_check() -> None:
    """Simple health check that runs alongside the bot."""
    log = get_logger("healthcheck")
    while True:
        try:
            redis_conn = create_redis_connection()
            redis_conn.ping()
            redis_conn.close()
            log.info("health_check_ok", component="redis")
        except Exception as exc:
            log.error("health_check_failed", component="redis", error=str(exc))
        await asyncio.sleep(30)


async def shutdown(bot: Bot, _dispatcher: Dispatcher) -> None:
    """Graceful shutdown handler."""
    log = get_logger("shutdown")
    log.info("shutdown_initiated")
    await bot.session.close()
    log.info("shutdown_complete")


async def run_bot_async() -> None:
    """Async entry point for the bot process."""
    configure_logging()
    settings = get_settings()

    bot = Bot(
        token=settings.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )

    dp = setup_dispatcher()

    # Start health check as background task
    health_task = asyncio.create_task(health_check())

    # Register shutdown handler
    async def on_shutdown(bot: Bot, dispatcher: Dispatcher) -> None:
        health_task.cancel()
        await shutdown(bot, dispatcher)

    dp.shutdown.register(on_shutdown)

    # Handle SIGTERM/SIGINT gracefully
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig,
            lambda: asyncio.create_task(shutdown(bot, dp)),
        )

    logger.info(
        "bot_starting",
        env=settings.APP_ENV,
        polling=True,
    )

    try:
        await dp.start_polling(bot)
    except Exception:
        logger.exception("bot_crashed")
        raise
    finally:
        health_task.cancel()
        await shutdown(bot, dp)


def run_bot() -> None:
    """Entry point for the bot process."""
    asyncio.run(run_bot_async())


if __name__ == "__main__":
    run_bot()
