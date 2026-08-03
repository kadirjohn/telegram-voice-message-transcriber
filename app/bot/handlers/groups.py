from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import ChatMemberUpdated, Message

from app.bot.filters.role_filter import RoleFilter
from app.db.enums import GroupStatus
from app.db.repositories.group_repository import GroupRepository
from app.services.authorization import AuthorizationService

router = Router(name="groups")
auth = AuthorizationService()
group_repo = GroupRepository()


@router.message(Command("approve_here"), RoleFilter.admin())
async def cmd_approve_here(message: Message) -> None:
    """Approve the current group (must be called inside the group)."""
    chat = message.chat
    if chat.type not in ("group", "supergroup"):
        await message.answer("Bu komut yalnızca gruplarda kullanılabilir.")
        return

    group = group_repo.approve(chat.id, message.from_user.id)
    if group is None:
        group = group_repo.upsert(chat.id, title=chat.title, username=chat.username)
        group_repo.approve(chat.id, message.from_user.id)

    await message.answer(
        "✅ Bu grup onaylandı. Artık sesli mesajlar çevrilecek."
    )


@router.message(Command("revoke_here"), RoleFilter.admin())
async def cmd_revoke_here(message: Message) -> None:
    """Revoke the current group."""
    chat = message.chat
    if chat.type not in ("group", "supergroup"):
        await message.answer("Bu komut yalnızca gruplarda kullanılabilir.")
        return

    group_repo.revoke(chat.id)
    await message.answer("⛔ Bu grubun erişimi iptal edildi.")


@router.message(Command("group_approve"), RoleFilter.admin())
async def cmd_group_approve(message: Message, command: CommandObject) -> None:
    """Approve a group by chat_id from private chat."""
    if not command.args:
        await message.answer("Kullanım: `/group_approve <chat_id>`")
        return
    try:
        chat_id = int(command.args.strip())
    except ValueError:
        await message.answer("Geçersiz chat_id.")
        return

    group = group_repo.approve(chat_id, message.from_user.id)
    if group is None:
        await message.answer(f"Grup `{chat_id}` bulunamadı. Önce botu gruba ekleyin.")
        return
    await message.answer(f"✅ `{chat_id}` ID'li grup onaylandı.")


@router.message(Command("group_revoke"), RoleFilter.admin())
async def cmd_group_revoke(message: Message, command: CommandObject) -> None:
    """Revoke a group by chat_id from private chat."""
    if not command.args:
        await message.answer("Kullanım: `/group_revoke <chat_id>`")
        return
    try:
        chat_id = int(command.args.strip())
    except ValueError:
        await message.answer("Geçersiz chat_id.")
        return

    group_repo.revoke(chat_id)
    await message.answer(f"⛔ `{chat_id}` ID'li grup iptal edildi.")


@router.message(Command("pending_groups"), RoleFilter.admin())
async def cmd_pending_groups(message: Message) -> None:
    """List all pending groups."""
    pending = group_repo.get_pending()
    if not pending:
        await message.answer("Bekleyen grup yok.")
        return
    lines = [
        f"• `{g.chat_id}` — {g.title or '(isimsiz)'}"
        for g in pending
    ]
    await message.answer("⏳ **Bekleyen Gruplar:**\n\n" + "\n".join(lines))


@router.message(Command("groups"), RoleFilter.admin())
async def cmd_groups(message: Message) -> None:
    """List all groups with their status."""
    from app.db.repositories.group_repository import GroupRepository

    repo = GroupRepository()
    all_groups = repo.get_all_by_status(GroupStatus.APPROVED) + \
                 repo.get_all_by_status(GroupStatus.PENDING) + \
                 repo.get_all_by_status(GroupStatus.REVOKED)

    if not all_groups:
        await message.answer("Hiç grup yok.")
        return

    lines = []
    for g in all_groups:
        status_icon = {"APPROVED": "✅", "PENDING": "⏳", "REVOKED": "⛔"}.get(
            g.status.value, "❓"
        )
        lines.append(f"{status_icon} `{g.chat_id}` — {g.title or '(isimsiz)'}")
    await message.answer("📋 **Gruplar:**\n\n" + "\n".join(lines))


@router.my_chat_member()
async def on_bot_chat_member_update(event: ChatMemberUpdated) -> None:
    """Handle bot being added/removed from a group."""
    chat = event.chat
    if chat.type not in ("group", "supergroup"):
        return

    new_status = event.new_chat_member.status
    group_repo.upsert(
        chat.id,
        title=chat.title,
        username=chat.username,
        bot_member_status=new_status,
    )

    if new_status in ("member", "administrator"):
        group = group_repo.get_by_chat_id(chat.id)
        if group and group.status == GroupStatus.PENDING:
            # Notify owner/admins
            pass
