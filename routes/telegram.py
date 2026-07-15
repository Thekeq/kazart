from __future__ import annotations

import hmac
import logging

from flask import Blueprint, abort, jsonify, request
from aiogram.types import Update

from config import settings
from loader import bot, dp, register_routers, runtime


telegram_bp = Blueprint("telegram", __name__, url_prefix="/telegram")
logger = logging.getLogger(__name__)


@telegram_bp.get("/health")
def health():
    return jsonify({"ok": True})


@telegram_bp.post("/webhook")
def webhook():
    if settings.bot_mode != "webhook":
        abort(404)

    received = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not settings.webhook_secret_token or not hmac.compare_digest(received, settings.webhook_secret_token):
        abort(403)

    register_routers()
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400)
    try:
        update = Update.model_validate(data, context={"bot": bot})
    except Exception:
        logger.warning("Invalid Telegram webhook payload", exc_info=True)
        update = None
    if update is None:
        abort(400)
    future = runtime.submit(dp.feed_update(bot, update))
    future.add_done_callback(_log_update_error)
    return jsonify({"ok": True})


def _log_update_error(future) -> None:
    try:
        future.result()
    except Exception:
        logger.exception("Telegram webhook update processing failed")
