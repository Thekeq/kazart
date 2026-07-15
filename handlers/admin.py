from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import settings
from loader import ADMIN_ID


router = Router(name="admin")


@router.message(Command("admin"))
async def admin_panel(message: Message) -> None:
    if message.from_user.id != ADMIN_ID:
        await message.answer("Access denied")
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Open admin panel", url=f"{settings.public_base_url}/admin")]
        ]
    )
    await message.answer("Admin panel:", reply_markup=keyboard)
