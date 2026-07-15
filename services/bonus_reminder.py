from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from config import settings
from db import DAILY_BONUS_AMOUNT, DataBase


logger = logging.getLogger(__name__)


def _open_app_keyboard(text: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text, web_app=WebAppInfo(url=settings.public_webapp_url))]]
    )


async def _send_reminder(bot: Bot, db: DataBase, telegram_id: int, text: str, button: str) -> None:
    try:
        await bot.send_message(telegram_id, text, reply_markup=_open_app_keyboard(button), parse_mode=None)
        db.mark_daily_reminder_sent(telegram_id)
        await asyncio.sleep(0.05)
    except Exception:
        logger.exception("Failed to send bonus reminder to %s", telegram_id)


async def daily_bonus_reminder_loop(bot: Bot, db: DataBase) -> None:
    await asyncio.sleep(10)
    while True:
        try:
            for telegram_id in db.users_due_daily_reminder(limit=200):
                await _send_reminder(
                    bot,
                    db,
                    telegram_id,
                    f"Your daily bonus is ready. Open KAZart and claim {DAILY_BONUS_AMOUNT} {settings.coin_name}.",
                    "Claim daily bonus",
                )
            for row in db.users_due_streak_warning(limit=200):
                last = db.parse_time(row["last_daily_bonus_at"])
                burn_at = last + timedelta(hours=48) if last else None
                hours_left = max(1, int((burn_at - datetime.now(timezone.utc)).total_seconds() // 3600)) if burn_at else 1
                await _send_reminder(
                    bot,
                    db,
                    int(row["telegram_id"]),
                    f"🔥 Твой стрик {row['daily_streak_count']} дн. сгорит примерно через {hours_left} ч! "
                    "Забери ежедневный бонус и сохрани серию.",
                    "Спасти стрик",
                )
        except Exception:
            logger.exception("Daily bonus reminder loop failed")
        await asyncio.sleep(1800)
