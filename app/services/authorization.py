from __future__ import annotations

from app.config import get_settings
from app.db.enums import UserRole
from app.db.repositories.user_repository import UserRepository


class AuthorizationService:
    """Business logic for role-based access control."""

    def __init__(self, user_repo: UserRepository | None = None) -> None:
        self._user_repo = user_repo or UserRepository()
        self._settings = get_settings()

    def bootstrap_owner(self) -> None:
        """Ensure the configured owner exists on startup."""
        owner_id = self._settings.OWNER_TELEGRAM_ID
        self._user_repo.upsert(owner_id, role=UserRole.OWNER)

    def get_role(self, telegram_id: int) -> UserRole:
        user = self._user_repo.get_by_telegram_id(telegram_id)
        if user is None:
            return UserRole.USER
        return user.role

    def is_owner(self, telegram_id: int) -> bool:
        return self.get_role(telegram_id) == UserRole.OWNER

    def is_admin(self, telegram_id: int) -> bool:
        role = self.get_role(telegram_id)
        return role in (UserRole.OWNER, UserRole.ADMIN)

    def is_owner_or_admin(self, telegram_id: int) -> bool:
        return self.is_admin(telegram_id)

    def add_admin(self, caller_id: int, target_id: int) -> str:
        """Promote a user to ADMIN. Only OWNER can do this."""
        if not self.is_owner(caller_id):
            return "Bu işlem için yalnızca sahip (owner) yetkilidir."

        if target_id == caller_id:
            return "Sahip kendini admin yapamaz."

        self._user_repo.upsert(target_id, role=UserRole.ADMIN)
        return f"✅ Kullanıcı `{target_id}` admin olarak atandı."

    def remove_admin(self, caller_id: int, target_id: int) -> str:
        """Demote an ADMIN to USER. Only OWNER can do this."""
        if not self.is_owner(caller_id):
            return "Bu işlem için yalnızca sahip (owner) yetkilidir."

        if target_id == caller_id:
            return "Sahip kendini kaldıramaz."

        user = self._user_repo.get_by_telegram_id(target_id)
        if user is None or user.role != UserRole.ADMIN:
            return "Bu kullanıcı admin değil."

        self._user_repo.set_role(target_id, UserRole.USER)
        return f"✅ Kullanıcı `{target_id}` adminlikten çıkarıldı."

    def list_admins(self) -> list[tuple[int, str]]:
        admins = self._user_repo.get_all_admins()
        return [(u.telegram_id, u.role.value) for u in admins]

    def register_user(self, telegram_id: int) -> None:
        """Auto-register a user if they don't exist yet."""
        self._user_repo.upsert(telegram_id)
