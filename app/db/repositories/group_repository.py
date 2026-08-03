from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import GroupStatus
from app.db.models.group import Group
from app.db.session import get_session


class GroupRepository:
    """Data access for the groups table."""

    def __init__(self, session: Session | None = None) -> None:
        self._session = session or get_session()

    def get_by_chat_id(self, chat_id: int) -> Group | None:
        return self._session.get(Group, chat_id)

    def upsert(
        self,
        chat_id: int,
        *,
        title: str | None = None,
        username: str | None = None,
        status: GroupStatus | None = None,
        bot_member_status: str | None = None,
    ) -> Group:
        group = self.get_by_chat_id(chat_id)
        if group is None:
            group = Group(
                chat_id=chat_id,
                title=title,
                username=username,
                status=status or GroupStatus.PENDING,
                bot_member_status=bot_member_status,
            )
            self._session.add(group)
        else:
            if title is not None:
                group.title = title
            if username is not None:
                group.username = username
            if status is not None:
                group.status = status
            if bot_member_status is not None:
                group.bot_member_status = bot_member_status
        self._session.commit()
        return group

    def approve(self, chat_id: int, approved_by: int) -> Group | None:
        group = self.get_by_chat_id(chat_id)
        if group is None:
            return None
        group.status = GroupStatus.APPROVED
        group.approved_by = approved_by
        group.approved_at = datetime.now(UTC)
        self._session.commit()
        return group

    def revoke(self, chat_id: int) -> Group | None:
        group = self.get_by_chat_id(chat_id)
        if group is None:
            return None
        group.status = GroupStatus.REVOKED
        self._session.commit()
        return group

    def get_all_by_status(self, status: GroupStatus) -> list[Group]:
        stmt = select(Group).where(Group.status == status).order_by(Group.created_at)
        return list(self._session.scalars(stmt).all())

    def get_pending(self) -> list[Group]:
        return self.get_all_by_status(GroupStatus.PENDING)

    def get_approved(self) -> list[Group]:
        return self.get_all_by_status(GroupStatus.APPROVED)

    def is_approved(self, chat_id: int) -> bool:
        group = self.get_by_chat_id(chat_id)
        if group is None:
            return False
        return group.status == GroupStatus.APPROVED and group.is_enabled
