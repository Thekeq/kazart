from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from config import settings
from db import DAILY_BONUS_AMOUNT, DataBase


logger = logging.getLogger(__name__)


async def daily_bonus_reminder_loop(bot: Bot, db: DataBase) -> None:
    await asyncio.sleep(10)
    while True:
        try:
            user_ids = db.users_due_daily_reminder(limit=200)
            for telegram_id in user_ids:
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="Claim daily bonus", web_app=WebAppInfo(url=settings.public_webapp_url))]
                    ]
                )
                try:
                    await bot.send_message(
                        telegram_id,
                        f"Your daily bonus is ready. Open KAZart and claim {DAILY_BONUS_AMOUNT} {settings.coin_name}.",
                        reply_markup=keyboard,
                        parse_mode=None,
                    )
                    db.mark_daily_reminder_sent(telegram_id)
                    await asyncio.sleep(0.05)
                except Exception:
                    logger.exception("Failed to send daily bonus reminder to %s", telegram_id)
        except Exception:
            logger.exception("Daily bonus reminder loop failed")
        await asyncio.sleep(1800)
