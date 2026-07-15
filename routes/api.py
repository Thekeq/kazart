from __future__ import annotations

import logging
import threading
import time
from functools import wraps
from typing import Any, Callable

from flask import Blueprint, g, jsonify, request

from config import settings
from db import WEEKLY_REWARD_AMOUNTS, BalanceError
from loader import (
    ADMIN_ID,
    COIN_NAME,
    bot,
    crash_service,
    db,
    notify_admin_error,
    notify_quests_ready,
    roulette_service,
    runtime,
)
from services.games import GameError, normalize_upgrader_target, play_dice, play_plinko, play_upgrader
from services.rate_limit import RateLimitExceeded, rate_limiter
from services.shop import create_stars_invoice_link, shop_items
from services.telegram_auth import TelegramAuthError, validate_init_data


api_bp = Blueprint("api", __name__, url_prefix="/api")
logger = logging.getLogger(__name__)
_bot_username_lock = threading.Lock()
_bot_username: str = ""
_bot_username_checked_at = 0.0
_BOT_USERNAME_TTL_SECONDS = 3600
_BOT_USERNAME_FAIL_TTL_SECONDS = 60


@api_bp.errorhandler(Exception)
def handle_api_exception(exc: Exception):
    logger.exception("Unhandled API error")
    notify_admin_error(f"{request.method} {request.path}: {type(exc).__name__}: {exc}")
    return jsonify({"ok": False, "error": "Internal server error"}), 500


def _after_game_hooks(telegram_id: int) -> None:
    """Fire-and-forget retention hooks; must never break the game response."""
    try:
        ready = db.quests_ready_notification(telegram_id)
        if ready:
            notify_quests_ready(telegram_id, ready)
    except Exception:
        logger.exception("After-game retention hook failed")


def require_webapp_auth(view: Callable) -> Callable:
    @wraps(view)
    def wrapped(*args, **kwargs):
        init_data = request.headers.get("X-Telegram-Init-Data", "")
        if not init_data and request.headers.get("Authorization", "").startswith("tma "):
            init_data = request.headers["Authorization"][4:]

        try:
            auth = validate_init_data(
                init_data=init_data,
                bot_token=settings.bot_token,
                max_age_seconds=settings.init_data_max_age_seconds,
            )
        except TelegramAuthError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 401

        g.telegram_user = auth.user
        g.user = db.ensure_user(auth.user, is_admin=int(auth.user["id"]) == ADMIN_ID)
        start_param = auth.raw.get("start_param", "")
        if start_param.startswith("ref_") and not g.user.get("referred_by"):
            try:
                db.apply_referral(int(auth.user["id"]), int(start_param.removeprefix("ref_")))
                g.user = db.get_user(int(auth.user["id"])) or g.user
            except ValueError:
                pass
        return view(*args, **kwargs)

    return wrapped


def require_legal_acceptance(view: Callable) -> Callable:
    @wraps(view)
    def wrapped(*args, **kwargs):
        if int(g.user.get("is_banned") or 0):
            return fail("Account is blocked. Contact support if you think this is a mistake.", 403)
        if settings.require_legal_acceptance and not g.user.get("legal_accepted_at"):
            return fail("Please accept the 18+ virtual-only terms before using this feature.", 451)
        return view(*args, **kwargs)

    return wrapped


def rate_limit(scope: str, limit_attr: str, window_attr: str) -> Callable:
    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapped(*args, **kwargs):
            key = str(g.user["telegram_id"])
            try:
                rate_limiter.hit(
                    scope=scope,
                    key=key,
                    limit=int(getattr(settings, limit_attr)),
                    window_seconds=int(getattr(settings, window_attr)),
                )
            except RateLimitExceeded as exc:
                response = jsonify(
                    {
                        "ok": False,
                        "error": "Too many requests. Please slow down.",
                        "retry_after": exc.retry_after,
                    }
                )
                response.headers["Retry-After"] = str(exc.retry_after)
                return response, 429
            return view(*args, **kwargs)

        return wrapped

    return decorator


def payload() -> dict[str, Any]:
    return request.get_json(silent=True) or {}


def ok(data: dict[str, Any] | None = None, status: int = 200):
    body = {"ok": True, "coin_name": COIN_NAME}
    if data:
        body.update(data)
    # Admin-only tuning fields must never reach the Mini App client.
    if isinstance(body.get("user"), dict):
        body["user"] = {key: value for key, value in body["user"].items() if key != "luck_factor"}
    return jsonify(body), status


def fail(message: str, status: int = 400):
    return jsonify({"ok": False, "error": message}), status


@api_bp.get("/me")
@api_bp.get("/profile")
@require_webapp_auth
@rate_limit("me", "state_poll_limit", "state_poll_window_seconds")
def me():
    return ok(
        {
            "user": g.user,
            "stats": db.user_stats(g.user["telegram_id"]),
            "bonus": db.daily_bonus_status(g.user["telegram_id"]),
            "limits": {"min_bet": settings.min_bet, "max_bet": settings.max_bet},
            "invite_link": make_invite_link(g.user["telegram_id"]),
        }
    )


@api_bp.get("/history")
@require_webapp_auth
@rate_limit("history", "state_poll_limit", "state_poll_window_seconds")
def history():
    raw_limit = request.args.get("limit", "50")
    try:
        limit = max(1, min(100, int(raw_limit)))
    except ValueError:
        limit = 50
    try:
        offset = max(0, min(5000, int(request.args.get("offset", "0"))))
    except ValueError:
        offset = 0
    rows = db.player_history(g.user["telegram_id"], limit=limit, offset=offset)
    return ok({"history": rows, "offset": offset, "limit": limit, "has_more": len(rows) == limit})


@api_bp.post("/settings/bonus-notify")
@require_webapp_auth
@require_legal_acceptance
@rate_limit("settings", "game_action_limit", "game_action_window_seconds")
def save_bonus_notify_settings():
    data = payload()
    enabled = bool(data.get("enabled"))
    user = db.set_bonus_notify_enabled(g.user["telegram_id"], enabled)
    return ok({"user": user})


@api_bp.get("/retention")
@require_webapp_auth
@require_legal_acceptance
@rate_limit("retention", "state_poll_limit", "state_poll_window_seconds")
def retention_status():
    return ok({"retention": db.retention_status(g.user["telegram_id"])})


@api_bp.post("/retention/quests/claim")
@require_webapp_auth
@require_legal_acceptance
@rate_limit("quest_claim", "bonus_claim_limit", "bonus_claim_window_seconds")
def claim_quest_reward():
    data = payload()
    try:
        result = db.claim_quest_reward(g.user["telegram_id"], str(data.get("quest_id", "")))
    except BalanceError as exc:
        return fail(str(exc))
    return ok(
        {
            "claim": result,
            "user": db.get_user(g.user["telegram_id"]),
            "retention": db.retention_status(g.user["telegram_id"]),
        }
    )


@api_bp.post("/retention/achievements/claim")
@require_webapp_auth
@require_legal_acceptance
@rate_limit("achievement_claim", "bonus_claim_limit", "bonus_claim_window_seconds")
def claim_achievement_reward():
    data = payload()
    try:
        result = db.claim_achievement(g.user["telegram_id"], str(data.get("achievement_id", "")))
    except BalanceError as exc:
        return fail(str(exc))
    return ok(
        {
            "claim": result,
            "user": db.get_user(g.user["telegram_id"]),
            "retention": db.retention_status(g.user["telegram_id"]),
        }
    )


@api_bp.post("/retention/season/claim")
@require_webapp_auth
@require_legal_acceptance
@rate_limit("season_claim", "bonus_claim_limit", "bonus_claim_window_seconds")
def claim_season_reward():
    data = payload()
    try:
        result = db.claim_season_reward(g.user["telegram_id"], data.get("level"), data.get("tier"))
    except BalanceError as exc:
        return fail(str(exc))
    return ok(
        {
            "claim": result,
            "user": db.get_user(g.user["telegram_id"]),
            "retention": db.retention_status(g.user["telegram_id"]),
        }
    )


@api_bp.post("/settings/cosmetic")
@require_webapp_auth
@require_legal_acceptance
@rate_limit("settings", "game_action_limit", "game_action_window_seconds")
def save_cosmetic_setting():
    data = payload()
    try:
        user = db.set_active_cosmetic(g.user["telegram_id"], data.get("cosmetic_id"))
    except BalanceError as exc:
        return fail(str(exc))
    return ok({"user": user, "retention": db.retention_status(g.user["telegram_id"])})


@api_bp.get("/games/upgrader/quote")
@require_webapp_auth
@require_legal_acceptance
@rate_limit("upgrader_quote", "state_poll_limit", "state_poll_window_seconds")
def upgrader_quote():
    multiplier = request.args.get("multiplier", "1.5")
    chance = request.args.get("chance")
    try:
        bet = max(0, int(request.args.get("bet", "0") or 0))
        target = normalize_upgrader_target(multiplier_value=multiplier, chance_value=chance)
    except (ValueError, GameError) as exc:
        return fail(str(exc))
    return ok(
        {
            "bet": bet,
            "multiplier": target["multiplier"],
            "chance": target["chance"],
            "potential_win": int(bet * target["multiplier"]),
        }
    )


@api_bp.post("/games/upgrader")
@require_webapp_auth
@require_legal_acceptance
@rate_limit("game_action", "game_action_limit", "game_action_window_seconds")
def upgrader():
    data = payload()
    try:
        target = normalize_upgrader_target(
            multiplier_value=data.get("multiplier"),
            chance_value=data.get("chance"),
        )
        db.set_upgrader_preference(g.user["telegram_id"], target["multiplier"], target["chance"])
        result = play_upgrader(
            db,
            g.user["telegram_id"],
            data.get("bet"),
            multiplier_value=target["multiplier"],
        )
    except (BalanceError, GameError) as exc:
        return fail(str(exc))
    _after_game_hooks(g.user["telegram_id"])
    return ok({"result": result})


@api_bp.post("/settings/upgrader")
@require_webapp_auth
@require_legal_acceptance
@rate_limit("settings", "game_action_limit", "game_action_window_seconds")
def save_upgrader_settings():
    data = payload()
    try:
        target = normalize_upgrader_target(
            multiplier_value=data.get("multiplier"),
            chance_value=data.get("chance"),
        )
        user = db.set_upgrader_preference(g.user["telegram_id"], target["multiplier"], target["chance"])
    except (BalanceError, GameError) as exc:
        return fail(str(exc))
    return ok({"user": user, "target": target})


@api_bp.post("/games/dice")
@require_webapp_auth
@require_legal_acceptance
@rate_limit("game_action", "game_action_limit", "game_action_window_seconds")
def dice():
    data = payload()
    try:
        result = play_dice(
            db,
            g.user["telegram_id"],
            data.get("bet"),
            data.get("chance", 50),
            data.get("direction", "under"),
        )
    except (BalanceError, GameError) as exc:
        return fail(str(exc))
    _after_game_hooks(g.user["telegram_id"])
    return ok({"result": result})


@api_bp.post("/games/plinko")
@require_webapp_auth
@require_legal_acceptance
@rate_limit("game_action", "game_action_limit", "game_action_window_seconds")
def plinko():
    data = payload()
    try:
        result = play_plinko(db, g.user["telegram_id"], data.get("bet"), data.get("risk", "medium"))
    except (BalanceError, GameError) as exc:
        return fail(str(exc))
    _after_game_hooks(g.user["telegram_id"])
    return ok({"result": result})


@api_bp.post("/games/crash/bet")
@require_webapp_auth
@require_legal_acceptance
@rate_limit("game_action", "game_action_limit", "game_action_window_seconds")
def crash_bet():
    data = payload()
    try:
        result = crash_service.place_bet(g.user["telegram_id"], data.get("bet"))
    except (BalanceError, GameError) as exc:
        return fail(str(exc))
    return ok({"result": result})


@api_bp.get("/games/crash/state")
@require_webapp_auth
@require_legal_acceptance
@rate_limit("crash_state", "state_poll_limit", "state_poll_window_seconds")
def crash_global_state():
    try:
        result = crash_service.state(g.user["telegram_id"])
    except (BalanceError, GameError) as exc:
        return fail(str(exc))
    return ok({"result": result})


@api_bp.post("/games/crash/cashout")
@require_webapp_auth
@require_legal_acceptance
@rate_limit("game_action", "game_action_limit", "game_action_window_seconds")
def crash_global_cashout():
    try:
        result = crash_service.cashout(g.user["telegram_id"])
    except (BalanceError, GameError) as exc:
        return fail(str(exc))
    _after_game_hooks(g.user["telegram_id"])
    return ok({"result": result})


@api_bp.post("/games/roulette/bet")
@require_webapp_auth
@require_legal_acceptance
@rate_limit("game_action", "game_action_limit", "game_action_window_seconds")
def roulette_bet():
    data = payload()
    try:
        result = roulette_service.place_bet(
            g.user["telegram_id"],
            data.get("bet"),
            data.get("number"),
            data.get("bet_type"),
            data.get("color"),
            data.get("range"),
        )
    except (BalanceError, GameError) as exc:
        return fail(str(exc))
    return ok({"result": result})


@api_bp.get("/games/roulette/state")
@require_webapp_auth
@require_legal_acceptance
@rate_limit("roulette_state", "state_poll_limit", "state_poll_window_seconds")
def roulette_state():
    try:
        result = roulette_service.state(g.user["telegram_id"])
    except (BalanceError, GameError) as exc:
        return fail(str(exc))
    return ok({"result": result})


@api_bp.get("/bonus/status")
@require_webapp_auth
@require_legal_acceptance
@rate_limit("bonus_status", "state_poll_limit", "state_poll_window_seconds")
def bonus_status():
    try:
        return ok({"bonus": db.daily_bonus_status(g.user["telegram_id"])})
    except BalanceError as exc:
        return fail(str(exc))


@api_bp.post("/bonus/daily")
@require_webapp_auth
@require_legal_acceptance
@rate_limit("bonus_claim", "bonus_claim_limit", "bonus_claim_window_seconds")
def claim_daily_bonus():
    try:
        result = db.claim_daily_bonus(g.user["telegram_id"])
    except BalanceError as exc:
        return fail(str(exc))
    return ok({"bonus": result, "user": db.get_user(g.user["telegram_id"])})


@api_bp.post("/legal/accept")
@require_webapp_auth
def legal_accept():
    user = db.mark_legal_accepted(g.user["telegram_id"])
    return ok({"user": user})


@api_bp.get("/leaderboard")
@require_webapp_auth
@require_legal_acceptance
@rate_limit("leaderboard", "state_poll_limit", "state_poll_window_seconds")
def leaderboard():
    period = request.args.get("period", "all")
    if period == "week":
        return ok(
            {
                "leaders": db.weekly_leaderboard(limit=100),
                "period": "week",
                "weekly_rewards": list(WEEKLY_REWARD_AMOUNTS),
            }
        )
    return ok({"leaders": db.leaderboard(limit=100), "period": "all"})


@api_bp.get("/shop/packages")
@require_webapp_auth
def shop_packages():
    return ok({"packages": shop_items()})


@api_bp.post("/shop/invoice")
@require_webapp_auth
@require_legal_acceptance
@rate_limit("shop_invoice", "shop_invoice_limit", "shop_invoice_window_seconds")
def shop_invoice():
    data = payload()
    kind = str(data.get("kind", ""))
    try:
        result = runtime.submit(create_stars_invoice_link(bot, kind)).result(timeout=15)
    except ValueError as exc:
        return fail(str(exc))
    except Exception:
        logger.exception("Failed to create Stars invoice (kind=%r)", kind)
        return fail("Failed to create the invoice. Please try again later.", 502)
    return ok({"invoice": result})


def make_invite_link(telegram_id: int) -> str:
    username = _cached_bot_username()
    if username:
        return f"https://t.me/{username}?start=ref_{telegram_id}"
    return f"ref_{telegram_id}"


def _bot_username_cache_fresh(now: float) -> bool:
    if not _bot_username_checked_at:
        return False
    ttl = _BOT_USERNAME_TTL_SECONDS if _bot_username else _BOT_USERNAME_FAIL_TTL_SECONDS
    return now - _bot_username_checked_at < ttl


def _cached_bot_username() -> str:
    global _bot_username, _bot_username_checked_at

    now = time.monotonic()
    if _bot_username_cache_fresh(now):
        return _bot_username

    with _bot_username_lock:
        now = time.monotonic()
        if _bot_username_cache_fresh(now):
            return _bot_username

        _bot_username_checked_at = now
        try:
            me = runtime.submit(bot.get_me()).result(timeout=8)
            _bot_username = (me.username or "").strip()
        except Exception:
            logger.warning("Failed to resolve bot username", exc_info=True)
        return _bot_username
