from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from app.bot.filters.role_filter import RoleFilter
from app.services.authorization import AuthorizationService

router = Router(name="admin")
auth = AuthorizationService()


@router.message(Command("admin_add"), RoleFilter.owner())
async def cmd_admin_add(message: Message, command: CommandObject) -> None:
    """Add an admin. Usage: /admin_add <telegram_id> or reply to a user."""
    target_id = _resolve_target_id(message, command)
    if target_id is None:
        await message.answer(
            "Kullanım: `/admin_add <telegram_id>` veya bir mesaja yanıt verin."
        )
        return
    result = auth.add_admin(message.from_user.id, target_id)
    await message.answer(result)


@router.message(Command("admin_remove"), RoleFilter.owner())
async def cmd_admin_remove(message: Message, command: CommandObject) -> None:
    """Remove an admin. Usage: /admin_remove <telegram_id> or reply."""
    target_id = _resolve_target_id(message, command)
    if target_id is None:
        await message.answer(
            "Kullanım: `/admin_remove <telegram_id>` veya bir mesaja yanıt verin."
        )
        return
    result = auth.remove_admin(message.from_user.id, target_id)
    await message.answer(result)


@router.message(Command("admins"), RoleFilter.owner())
async def cmd_admins(message: Message) -> None:
    """List all admins."""
    admins = auth.list_admins()
    if not admins:
        await message.answer("Henüz hiç admin yok.")
        return
    lines = [f"• `{tid}` — {role}" for tid, role in admins]
    await message.answer("📋 **Admin Listesi:**\n\n" + "\n".join(lines))


@router.message(Command("stats"), RoleFilter.owner())
async def cmd_stats(message: Message) -> None:
    """Show basic operational statistics."""
    from app.db.repositories.group_repository import GroupRepository

    group_repo = GroupRepository()

    pending = len(group_repo.get_pending())
    approved = len(group_repo.get_approved())

    await message.answer(
        "📊 **İstatistikler:**\n\n"
        f"• Bekleyen grup: {pending}\n"
        f"• Onaylanan grup: {approved}\n"
    )


def _resolve_target_id(message: Message, command: CommandObject) -> int | None:
    """Extract target user ID from command args or reply."""
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id
    if command.args:
        try:
            return int(command.args.strip())
        except ValueError:
            return None
    return None
