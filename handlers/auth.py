from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from config import settings
from loader import ADMIN_ID, db


router = Router(name="auth")


@router.message(CommandStart())
async def start(message: Message, command: CommandObject) -> None:
    db.ensure_user(message.from_user, is_admin=message.from_user.id == ADMIN_ID)
    if command.args and command.args.startswith("ref_"):
        try:
            referrer_id = int(command.args.removeprefix("ref_"))
            db.apply_referral(message.from_user.id, referrer_id)
        except ValueError:
            pass
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Open Mini App", web_app=WebAppInfo(url=settings.public_webapp_url))]
        ]
    )
    await message.answer(
        "Open KAZart Mini App.\n\n"
        "18+ entertainment only. Virtual coins have no cash value: no cash out, no prizes, no real-money winnings.",
        reply_markup=keyboard,
    )
