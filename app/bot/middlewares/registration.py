from __future__ import annotations

from collections.abc import Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

from app.services.authorization import AuthorizationService


class RegistrationMiddleware(BaseMiddleware):
    """Auto-register any user who interacts with the bot."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Any],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        if user is not None:
            auth = AuthorizationService()
            auth.register_user(user.id)
        return await handler(event, data)
