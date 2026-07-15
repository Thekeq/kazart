from __future__ import annotations

import asyncio
import html
import logging
import threading
import time
from concurrent.futures import Future
from typing import Coroutine

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from config import settings
from db import DataBase
from services.games import CrashService, RouletteService
from services.maintenance import backup_sqlite_database, configure_logging


configure_logging(settings)
logger = logging.getLogger(__name__)


BOT_TOKEN = settings.bot_token
ADMIN_ID = settings.admin_id
COIN_NAME = settings.coin_name

bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(disable_fsm=True)
if settings.backup_on_start:
    try:
        backup_sqlite_database(settings.database_path, settings.backup_dir, keep=settings.backup_keep)
    except Exception:
        logger.exception("SQLite startup backup failed")
db = DataBase(settings.database_path)
crash_service = CrashService(db)
roulette_service = RouletteService(db)

_routers_registered = False
_polling_future: Future | None = None
_bot_tasks_started = False
_game_ticker_started = False
GAME_TICK_INTERVAL_SECONDS = 1.0


class AsyncRuntime:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, name="telegram-runtime", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def submit(self, coro: Coroutine) -> Future:
        return asyncio.run_coroutine_threadsafe(coro, self.loop)


runtime = AsyncRuntime()


def register_routers() -> None:
    global _routers_registered
    if _routers_registered:
        return

    from handlers import admin, auth, common

    dp.include_router(auth.router)
    dp.include_router(common.router)
    dp.include_router(admin.router)
    _routers_registered = True


async def _start_bot_background_tasks() -> None:
    try:
        await bot.set_my_commands(
            [
                BotCommand(command="app", description="Open Mini App"),
                BotCommand(command="balance", description="Show virtual balance"),
                BotCommand(command="terms", description="Terms of Use"),
                BotCommand(command="privacy", description="Privacy Policy"),
                BotCommand(command="support", description="Support contacts"),
                BotCommand(command="paysupport", description="Stars payment support"),
            ]
        )
    except Exception:
        logger.exception("Failed to set bot commands")

    from services.bonus_reminder import daily_bonus_reminder_loop

    asyncio.create_task(daily_bonus_reminder_loop(bot, db))


def start_bot_background_tasks() -> None:
    """Bot menu commands + daily bonus reminders, for both polling and webhook modes."""
    global _bot_tasks_started
    if _bot_tasks_started:
        return
    _bot_tasks_started = True
    runtime.submit(_start_bot_background_tasks())


_MAINTENANCE_INTERVAL_SECONDS = 60.0
_BACKUP_INTERVAL_SECONDS = 24 * 3600.0
_ADMIN_ALERT_COOLDOWN_SECONDS = 600.0
_last_admin_alert_at = 0.0
_admin_alert_lock = threading.Lock()


def notify_admin_error(summary: str) -> None:
    """Push a throttled error alert to the admin's Telegram (max 1 per 10 min)."""
    global _last_admin_alert_at
    if not ADMIN_ID:
        return
    now = time.monotonic()
    with _admin_alert_lock:
        if now - _last_admin_alert_at < _ADMIN_ALERT_COOLDOWN_SECONDS:
            return
        _last_admin_alert_at = now
    try:
        safe = html.escape(summary[:500])
        runtime.submit(bot.send_message(ADMIN_ID, f"⚠️ KAZart error:\n<code>{safe}</code>"))
    except Exception:
        logger.exception("Failed to send admin error alert")


def _notify_weekly_winners(winners: list[dict]) -> None:
    for winner in winners:
        place_emoji = {1: "🥇", 2: "🥈", 3: "🥉"}.get(winner["place"], "🏆")
        text = (
            f"{place_emoji} Ты занял {winner['place']} место в недельном топе KAZart "
            f"и получил {winner['amount']} {COIN_NAME}! Награда уже на балансе."
        )
        try:
            runtime.submit(bot.send_message(winner["telegram_id"], text))
        except Exception:
            logger.exception("Failed to notify weekly winner %s", winner["telegram_id"])


def notify_quests_ready(telegram_id: int, ready_count: int) -> None:
    text = (
        f"🎯 У тебя {ready_count} выполненных квестов с несобранными наградами. "
        "Загляни в Mini App и забери их!"
    )
    try:
        runtime.submit(bot.send_message(telegram_id, text))
    except Exception:
        logger.exception("Failed to send quest notification to %s", telegram_id)


def _run_maintenance(now: float, state: dict) -> None:
    if now >= state["next_backup_at"]:
        state["next_backup_at"] = now + _BACKUP_INTERVAL_SECONDS
        if settings.database_path != ":memory:":
            try:
                backup_sqlite_database(settings.database_path, settings.backup_dir, keep=settings.backup_keep)
            except Exception:
                logger.exception("Periodic SQLite backup failed")
    try:
        winners = db.payout_weekly_rewards()
        if winners:
            logger.info("Weekly rewards paid: %s", winners)
            _notify_weekly_winners(winners)
    except Exception:
        logger.exception("Weekly rewards payout failed")


def _game_tick_loop() -> None:
    # Shared Crash/Roulette rounds must progress and finalize pending bets even
    # when nobody is polling the state API.
    maintenance_state = {"next_backup_at": time.monotonic() + _BACKUP_INTERVAL_SECONDS}
    next_maintenance_at = time.monotonic() + _MAINTENANCE_INTERVAL_SECONDS
    while True:
        try:
            crash_service.state()
        except Exception:
            logger.exception("Crash ticker failed")
        try:
            roulette_service.state()
        except Exception:
            logger.exception("Roulette ticker failed")
        now = time.monotonic()
        if now >= next_maintenance_at:
            next_maintenance_at = now + _MAINTENANCE_INTERVAL_SECONDS
            try:
                _run_maintenance(now, maintenance_state)
            except Exception:
                logger.exception("Maintenance lane failed")
        time.sleep(GAME_TICK_INTERVAL_SECONDS)


def start_game_ticker() -> None:
    global _game_ticker_started
    if _game_ticker_started:
        return
    _game_ticker_started = True
    threading.Thread(target=_game_tick_loop, name="game-ticker", daemon=True).start()


async def _run_polling() -> None:
    register_routers()
    await bot.delete_webhook(drop_pending_updates=settings.drop_pending_updates)
    logger.info("Telegram polling started")
    await dp.start_polling(
        bot,
        allowed_updates=dp.resolve_used_update_types(),
        handle_signals=False,
    )


def _log_polling_exit(future: Future) -> None:
    try:
        future.result()
    except Exception:
        logger.exception("Telegram polling stopped unexpectedly")


def start_polling_in_background() -> Future:
    global _polling_future
    if _polling_future and not _polling_future.done():
        return _polling_future

    _polling_future = runtime.submit(_run_polling())
    _polling_future.add_done_callback(_log_polling_exit)
    return _polling_future
