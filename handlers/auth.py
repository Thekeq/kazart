from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from config import settings
from db import BalanceError
from loader import ADMIN_ID, COIN_NAME, db


router = Router(name="auth")


@router.message(CommandStart())
async def start(message: Message, command: CommandObject) -> None:
    db.ensure_user(message.from_user, is_admin=message.from_user.id == ADMIN_ID)
    promo_note = ""
    args = command.args or ""
    if args.startswith("ref_"):
        try:
            referrer_id = int(args.removeprefix("ref_"))
            db.apply_referral(message.from_user.id, referrer_id)
        except ValueError:
            pass
    elif args.startswith("promo_"):
        try:
            result = db.redeem_promo_code(message.from_user.id, args.removeprefix("promo_"))
            if result.get("reward_kind") == "coins":
                promo_note = f"🎁 Промокод активирован: +{result['reward_value']} {COIN_NAME}!\n\n"
            else:
                label = "Premium" if result.get("reward_kind") == "premium" else "Season Pass"
                promo_note = f"🎁 Промокод активирован: {label} на {result['reward_value']} дн.!\n\n"
        except BalanceError:
            pass
    elif args.startswith("src_"):
        try:
            db.apply_source(message.from_user.id, args.removeprefix("src_"))
        except BalanceError:
            pass
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Open Mini App", web_app=WebAppInfo(url=settings.public_webapp_url))]
        ]
    )
    await message.answer(
        f"{promo_note}Open KAZart Mini App.\n\n"
        "18+ entertainment only. Virtual coins have no cash value: no cash out, no prizes, no real-money winnings.",
        reply_markup=keyboard,
        parse_mode=None,
    )
