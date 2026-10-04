from datetime import datetime, timezone
from dataclasses import dataclass, asdict

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.enums import ChatType
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import supabase
from .assign_lead import get_assignee_for_category


router = Router()
router.message.filter(F.chat.type == ChatType.PRIVATE)


def get_chat_id():
    result = (
        supabase
        .table("chats")
        .select("chat_id")
        .limit(1)
        .execute()
    )

    if not result.data:
        return None

    return int(result.data[0]["chat_id"])


@dataclass
class TeamMember:
    telegram_id: int
    telegram_username: str | None = None
    display_name: str | None = None
    is_admin: bool = False
    can_receive_leads: bool = True
    status: str = "OFFLINE"
    is_active: bool = True


class AddLeadState(StatesGroup):
    waiting_for_link = State()


# START
@router.message(CommandStart())
async def start_handler(message: Message):
    user = message.from_user

    existing = (
        supabase
        .table("team_members")
        .select("id")
        .eq("telegram_id", user.id)
        .execute()
    )

    # Do NOT overwrite admin/status/etc every time /start is used
    if existing.data:
        (
            supabase
            .table("team_members")
            .update({
                "telegram_username": user.username,
                "display_name": user.first_name,
            })
            .eq("telegram_id", user.id)
            .execute()
        )

    else:
        member = TeamMember(
            telegram_id=user.id,
            telegram_username=user.username,
            display_name=user.first_name,
        )

        (
            supabase
            .table("team_members")
            .insert(asdict(member))
            .execute()
        )

    await message.answer(
        f"Успешно зарегистрировались!\n"
        f"Ваш ID пользователя: {user.id}"
    )


# CHANGE STATUS
@router.message(Command("change_status"))
async def change_status_handler(message: Message):
    user = message.from_user

    check_status = (
        supabase
        .table("team_members")
        .select("status")
        .eq("telegram_id", user.id)
        .execute()
    )

    if not check_status.data:
        await message.answer(
            "ВЫ еще не зарегистрированы, используйте /start."
        )
        return

    current_status = check_status.data[0]["status"]

    if current_status == "OFFLINE":
        new_status = "ONLINE"
    else:
        new_status = "OFFLINE"

    (
        supabase
        .table("team_members")
        .update({
            "status": new_status
        })
        .eq("telegram_id", user.id)
        .execute()
    )

    await message.answer(
        f"Ваш статус поменян на: {new_status}"
    )

    chat_id = get_chat_id()

    if chat_id:
        await message.bot.send_message(
            chat_id=chat_id,
            text=f"{user.first_name} --> {new_status}"
        )


# RESET ALL STATUS
@router.message(Command("reset_all_status"))
async def reset_all_status_handler(message: Message):
    admin_check = (
        supabase
        .table("team_members")
        .select("is_admin")
        .eq("telegram_id", message.from_user.id)
        .execute()
    )

    if (
        not admin_check.data
        or not admin_check.data[0]["is_admin"]
    ):
        await message.answer(
            "У вас нету прав чтобы использовать эту команду."
        )
        return

    (
        supabase
        .table("team_members")
        .update({
            "status": "OFFLINE"
        })
        .neq("telegram_id", 0)
        .execute()
    )

    await message.answer(
        "Все статусы поменяны на: OFFLINE"
    )

    chat_id = get_chat_id()

    if chat_id:
        await message.bot.send_message(
            chat_id=chat_id,
            text="Good Night Team UwU <3",
            parse_mode=None
        )


# ADD LEAD
@router.message(Command("add_lead"))
async def add_lead_handler(message: Message):
    categories = (
        supabase
        .table("categories")
        .select("id, name")
        .eq("is_active", True)
        .order("sort_order")
        .execute()
    )

    if not categories.data:
        await message.answer("Нет доступных категорий.")
        return

    buttons = [
        InlineKeyboardButton(
            text=category["name"],
            callback_data=f"lead_category:{category['id']}"
        )
        for category in categories.data
    ]

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            buttons[i:i + 3]
            for i in range(0, len(buttons), 3)
        ]
    )

    await message.answer(
        "Выберите категорию:",
        reply_markup=keyboard
    )

# CATEGORY SELECTED
@router.callback_query(
    F.data.startswith("lead_category:")
)
async def lead_category_handler(
    callback: CallbackQuery,
    state: FSMContext
):
    category_id = callback.data.split(":", 1)[1]

    await state.update_data(
        current_category_id=category_id
    )

    await state.set_state(
        AddLeadState.waiting_for_link
    )

    await callback.message.edit_reply_markup(
        reply_markup=None
    )

    await callback.message.answer(
        "Отправьте ссылку на лид:"
    )
    await callback.answer()


# RECEIVE LEAD LINK
@router.message(AddLeadState.waiting_for_link)
async def lead_link_handler(
    message: Message,
    state: FSMContext
):
    user = message.from_user

    if not message.text:
        await message.answer(
            "Пожалуйста, отправьте действительную ссылку."
        )
        return

    lead_url = message.text.strip()

    if not lead_url.startswith(
        ("http://", "https://")
    ):
        await message.answer(
            "Отправьте действительную ссылку."
        )
        return

    state_data = await state.get_data()

    category_id = state_data[
        "current_category_id"
    ]

    # Get internal team_members UUID
    submitter_result = (
        supabase
        .table("team_members")
        .select("id")
        .eq("telegram_id", user.id)
        .execute()
    )

    if not submitter_result.data:
        await message.answer(
            "Вы не зарегистрированы. Используйте /start."
        )

        await state.clear()
        return

    submitter_id = (
        submitter_result.data[0]["id"]
    )

    category_result = (
        supabase
        .table("categories")
        .select("code, name, is_distributable")
        .eq("id", category_id)
        .single()
        .execute()
    )

    category = category_result.data


    category_code = category["code"]
    category_name = category["name"]
    is_distributable = category["is_distributable"]

    if category_code == "trash":
        assignee_id = None

    elif is_distributable:
        assignee_id = get_assignee_for_category(
            category_id
        )

    else:
        await message.answer(
            "Эта категория сейчас не распределяется."
        )
        await state.clear()
        return
    lead = {
        "lead_url": lead_url,
        "original_category_id": category_id,
        "current_category_id": category_id,
        "assignee_id": assignee_id,
        "submitted_by_id": submitter_id,
        "submitted_by_username": user.username,
}   
    if assignee_id is not None:
        lead["assigned_at"] = (
            datetime.now(timezone.utc)
            .isoformat()
        )

    insert_result = (
        supabase
        .table("leads")
        .insert(lead)
        .execute()
    )
    
    await state.clear()
    
    if category_code == "trash":
        await message.answer(
            "Лид сохранен как мусор."
        )
        return

    if assignee_id is None:
        await message.answer(
            "Лид добавлен\n"
            "Нету онлайн мемберов чтобы назначить лид. Лид будет назначен когда кто-то станет онлайн."
        )
        return

    # Get assignee information
    assignee_result = (
        supabase
        .table("team_members")
        .select(
            "display_name, telegram_id"
        )
        .eq("id", assignee_id)
        .execute()
    )
    
    if not assignee_result.data:
        await message.answer(
            "Лид добавлен и назначен."
        )
        return

    assignee = assignee_result.data[0]

    await message.answer(
        f"Лид добавлен.\n"
        f"Лид назначен: {assignee['display_name']}"
    )




# CANCEL FSM
@router.message(Command("cancel"))
async def cancel_handler(
    message: Message,
    state: FSMContext
):
    await state.clear()

    await message.answer(
        "Отменено."
    )