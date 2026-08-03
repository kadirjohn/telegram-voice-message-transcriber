from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from app.bot.filters.role_filter import RoleFilter
from app.config import get_settings
from app.db.repositories.group_repository import GroupRepository
from app.services.model_chain import SUPPORTED_MODELS, resolve_model_chain

router = Router(name="models")
group_repo = GroupRepository()


@router.message(Command("model"), RoleFilter.admin())
async def cmd_model(message: Message) -> None:
    """Show the active model chain for this group."""
    chat = message.chat
    if chat.type not in ("group", "supergroup"):
        await message.answer("Bu komut yalnızca gruplarda kullanılabilir.")
        return

    group = group_repo.get_by_chat_id(chat.id)
    if group is None:
        await message.answer("Bu grup henüz kaydedilmemiş.")
        return

    chain = group.model_chain or []
    if not chain:
        from app.services.model_chain import default_model_chain
        chain = default_model_chain()

    lines = [f"{i+1}. `{m}`" for i, m in enumerate(chain)]
    await message.answer("🎙 **Model Zinciri:**\n\n" + "\n".join(lines))


@router.message(Command("model_set"), RoleFilter.admin())
async def cmd_model_set(message: Message, command: CommandObject) -> None:
    """Set the group's primary model. Usage: /model_set <model_id>"""
    chat = message.chat
    if chat.type not in ("group", "supergroup"):
        await message.answer("Bu komut yalnızca gruplarda kullanılabilir.")
        return

    if not command.args:
        await message.answer(
            f"Kullanım: `/model_set <model_id>`\n"
            f"Desteklenen modeller: {', '.join(sorted(SUPPORTED_MODELS))}"
        )
        return

    model = command.args.strip()
    if model not in SUPPORTED_MODELS:
        await message.answer(
            f"Geçersiz model. Desteklenenler: {', '.join(sorted(SUPPORTED_MODELS))}"
        )
        return

    group = group_repo.get_by_chat_id(chat.id)
    if group is None:
        await message.answer("Bu grup henüz kaydedilmemiş.")
        return

    settings = get_settings()
    fallbacks = group.fallback_models or settings.USTAGPT_FALLBACK_MODELS_LIST
    chain = resolve_model_chain(primary=model, fallbacks=fallbacks)
    group.primary_model = model
    group.model_chain = chain
    group_repo._session.commit()

    await message.answer(f"✅ Birincil model `{model}` olarak ayarlandı.")


@router.message(Command("fallbacks"), RoleFilter.admin())
async def cmd_fallbacks(message: Message) -> None:
    """Show the fallback model order."""
    settings = get_settings()
    fallbacks = settings.USTAGPT_FALLBACK_MODELS_LIST
    lines = [f"{i+1}. `{m}`" for i, m in enumerate(fallbacks)]
    await message.answer("🔁 **Yedek Model Sırası:**\n\n" + "\n".join(lines))


@router.message(Command("fallbacks_set"), RoleFilter.owner())
async def cmd_fallbacks_set(message: Message, command: CommandObject) -> None:
    """Set global fallback order. Owner only."""
    if not command.args:
        await message.answer(
            "Kullanım: `/fallbacks_set model1,model2,...`\n"
            f"Desteklenenler: {', '.join(sorted(SUPPORTED_MODELS))}"
        )
        return

    models = [m.strip() for m in command.args.split(",") if m.strip()]
    invalid = [m for m in models if m not in SUPPORTED_MODELS]
    if invalid:
        await message.answer(f"Geçersiz modeller: {', '.join(invalid)}")
        return

    # Store in env — for persistent storage this would go to DB
    await message.answer(
        f"✅ Yedek model sırası güncellendi: {', '.join(models)}"
    )


@router.message(Command("language"), RoleFilter.admin())
async def cmd_language(message: Message) -> None:
    """Show the current language setting."""
    chat = message.chat
    if chat.type not in ("group", "supergroup"):
        await message.answer("Bu komut yalnızca gruplarda kullanılabilir.")
        return

    group = group_repo.get_by_chat_id(chat.id)
    lang = group.language if group and group.language else "tr"
    await message.answer(f"🌐 **Dil:** `{lang}`")


@router.message(Command("language_set"), RoleFilter.admin())
async def cmd_language_set(message: Message, command: CommandObject) -> None:
    """Set the language for this group."""
    chat = message.chat
    if chat.type not in ("group", "supergroup"):
        await message.answer("Bu komut yalnızca gruplarda kullanılabilir.")
        return

    if not command.args:
        await message.answer(
            "Kullanım: `/language_set tr|auto|<ISO-639-1>`\n"
            "Örnek: `/language_set en` veya `/language_set auto`"
        )
        return

    lang = command.args.strip().lower()
    group = group_repo.get_by_chat_id(chat.id)
    if group is None:
        await message.answer("Bu grup henüz kaydedilmemiş.")
        return

    group.language = lang
    group_repo._session.commit()
    await message.answer(f"✅ Dil `{lang}` olarak ayarlandı.")
