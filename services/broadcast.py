from __future__ import annotations

import asyncio
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


@dataclass
class BroadcastResult:
    total: int
    sent: int
    failed: int


async def _send_one(
    bot: Bot,
    telegram_id: int,
    text: str,
    photo_url: str,
    markup: InlineKeyboardMarkup | None,
) -> None:
    if photo_url:
        await bot.send_photo(
            chat_id=telegram_id,
            photo=photo_url,
            caption=text or None,
            reply_markup=markup,
            parse_mode=None,
        )
    else:
        await bot.send_message(
            chat_id=telegram_id,
            text=text,
            reply_markup=markup,
            parse_mode=None,
        )


async def send_broadcast(
    bot: Bot,
    user_ids: list[int],
    text: str,
    photo_url: str = "",
    button_text: str = "",
    button_url: str = "",
) -> BroadcastResult:
    markup = None
    if button_text and button_url:
        markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=button_text, url=button_url)]]
        )

    sent = 0
    failed = 0
    for telegram_id in user_ids:
        try:
            await _send_one(bot, telegram_id, text, photo_url, markup)
            sent += 1
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 0.5)
            try:
                await _send_one(bot, telegram_id, text, photo_url, markup)
                sent += 1
            except TelegramAPIError:
                failed += 1
        except TelegramAPIError:
            failed += 1
        await asyncio.sleep(0.035)

    return BroadcastResult(total=len(user_ids), sent=sent, failed=failed)
