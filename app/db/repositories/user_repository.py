from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import UserRole
from app.db.models.user import User
from app.db.session import get_session


class UserRepository:
    """Data access for the users table."""

    def __init__(self, session: Session | None = None) -> None:
        self._session = session or get_session()

    def get_by_telegram_id(self, telegram_id: int) -> User | None:
        return self._session.get(User, telegram_id)

    def upsert(self, telegram_id: int, *, role: UserRole | None = None) -> User:
        user = self.get_by_telegram_id(telegram_id)
        if user is None:
            user = User(
                telegram_id=telegram_id,
                role=role or UserRole.USER,
            )
            self._session.add(user)
        elif role is not None:
            user.role = role
        self._session.commit()
        return user

    def set_role(self, telegram_id: int, role: UserRole) -> User | None:
        user = self.get_by_telegram_id(telegram_id)
        if user is None:
            return None
        user.role = role
        self._session.commit()
        return user

    def get_all_by_role(self, role: UserRole) -> list[User]:
        stmt = select(User).where(User.role == role, User.is_active.is_(True))
        return list(self._session.scalars(stmt).all())

    def get_all_admins(self) -> list[User]:
        return self.get_all_by_role(UserRole.ADMIN)

    def count_by_role(self, role: UserRole) -> int:
        stmt = select(User).where(User.role == role, User.is_active.is_(True))
        return len(list(self._session.scalars(stmt).all()))
