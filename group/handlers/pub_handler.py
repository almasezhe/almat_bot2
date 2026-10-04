from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram import Router, F
from aiogram.enums import ChatType

from database import supabase

router = Router()

router.message.filter(
    F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP})
)


@router.message(CommandStart())
async def start_handler(message: Message):
    chat = message.chat

    data = {
        "chat_id": chat.id,
    }

    supabase.table("chats").upsert(
        data,
        on_conflict="chat_id"
    ).execute()

    await message.answer(
        f"Чат сохранен!\n"
        f"Chat ID: {chat.id}"
    )
