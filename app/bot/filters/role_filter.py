from __future__ import annotations

from aiogram.filters import Filter
from aiogram.types import Message

from app.db.enums import UserRole
from app.services.authorization import AuthorizationService


class RoleFilter(Filter):
    """Aiogram filter that checks the caller's global application role."""

    def __init__(self, role: UserRole | None = None, admin: bool = False) -> None:
        self._role = role
        self._admin = admin

    @classmethod
    def owner(cls) -> RoleFilter:
        return cls(role=UserRole.OWNER)

    @classmethod
    def admin(cls) -> RoleFilter:
        return cls(admin=True)

    async def __call__(self, message: Message) -> bool:
        user_id = message.from_user.id if message.from_user else 0
        auth = AuthorizationService()

        if self._role == UserRole.OWNER:
            return auth.is_owner(user_id)
        if self._admin:
            return auth.is_admin(user_id)
        return True
