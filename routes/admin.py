from __future__ import annotations

import hmac
import logging
import secrets
import threading
import time
from collections import defaultdict, deque
from functools import wraps
from typing import Callable
from urllib.parse import urlparse

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from config import settings
from db import BalanceError
from loader import COIN_NAME, bot, db, runtime
from services.broadcast import send_broadcast


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
LOGIN_ATTEMPT_LIMIT = 5
LOGIN_ATTEMPT_WINDOW_SECONDS = 600
_login_attempts = defaultdict(deque)
logger = logging.getLogger(__name__)
_broadcast_jobs = deque(maxlen=20)
_broadcast_jobs_guard = threading.Lock()


def csrf_token() -> str:
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


@admin_bp.context_processor
def inject_csrf_token():
    return {"csrf_token": csrf_token}


@admin_bp.before_request
def protect_admin_posts():
    if request.method != "POST":
        return None
    token = session.get("_csrf_token")
    submitted = request.form.get("_csrf_token", "")
    if not token or not hmac.compare_digest(token, submitted):
        abort(400)
    return None


@admin_bp.after_request
def admin_security_headers(response):
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Cache-Control", "no-store")
    return response


def require_admin(view: Callable) -> Callable:
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("admin_id") != settings.admin_id:
            return redirect(url_for("admin.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def _client_key() -> str:
    # X-Forwarded-For is client-controlled unless a trusted reverse proxy sets it,
    # so honor it only when TRUST_PROXY_HEADERS is enabled.
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",", 1)[0].strip()
    return request.remote_addr or "unknown"


def _login_retry_after(key: str) -> int:
    now = time.monotonic()
    attempts = _login_attempts.get(key)
    if not attempts:
        return 0
    while attempts and now - attempts[0] >= LOGIN_ATTEMPT_WINDOW_SECONDS:
        attempts.popleft()
    if not attempts:
        _login_attempts.pop(key, None)
        return 0
    if len(attempts) < LOGIN_ATTEMPT_LIMIT:
        return 0
    return max(1, int(LOGIN_ATTEMPT_WINDOW_SECONDS - (now - attempts[0])))


def _record_login_failure(key: str) -> None:
    _login_attempts[key].append(time.monotonic())


def _clear_login_failures(key: str) -> None:
    _login_attempts.pop(key, None)


def _safe_admin_next(raw_next: str | None) -> str:
    if not raw_next:
        return url_for("admin.dashboard")
    parsed = urlparse(raw_next)
    if parsed.scheme or parsed.netloc or not raw_next.startswith("/admin"):
        return url_for("admin.dashboard")
    return raw_next


def _broadcast_jobs_snapshot() -> list[dict]:
    with _broadcast_jobs_guard:
        return [dict(job) for job in _broadcast_jobs]


def _finish_broadcast_job(job: dict, future) -> None:
    finished_at = db.now()
    try:
        result = future.result()
    except Exception as exc:
        logger.exception("Broadcast job failed", extra={"job_id": job.get("id")})
        updates = {"status": "failed", "error": str(exc), "finished_at": finished_at}
    else:
        logger.info(
            "Broadcast job complete",
            extra={"job_id": job.get("id"), "sent": result.sent, "total": result.total, "failed": result.failed},
        )
        updates = {
            "status": "complete",
            "sent": result.sent,
            "total": result.total,
            "failed": result.failed,
            "finished_at": finished_at,
        }
    with _broadcast_jobs_guard:
        job.update(updates)


@admin_bp.get("/login")
def login():
    return render_template("admin/login.html", has_password=bool(settings.admin_password))


@admin_bp.post("/login")
def login_post():
    if not settings.admin_password:
        flash("Set ADMIN_PASSWORD in .env before using the web admin panel.", "error")
        return redirect(url_for("admin.login"))

    key = _client_key()
    retry_after = _login_retry_after(key)
    if retry_after:
        flash(f"Too many login attempts. Try again in {retry_after} seconds.", "error")
        return redirect(url_for("admin.login"))

    password = request.form.get("password", "")
    if not hmac.compare_digest(password, settings.admin_password):
        _record_login_failure(key)
        flash("Bad password.", "error")
        return redirect(url_for("admin.login"))

    _clear_login_failures(key)
    session.clear()
    session["admin_id"] = settings.admin_id
    return redirect(_safe_admin_next(request.args.get("next")))


@admin_bp.post("/logout")
@require_admin
def logout():
    session.clear()
    return redirect(url_for("admin.login"))


@admin_bp.get("/")
@require_admin
def dashboard():
    return render_template(
        "admin/dashboard.html",
        stats=db.admin_overview(),
        games=db.recent_games(limit=25),
        payments=db.recent_payments(limit=10),
        coin_name=COIN_NAME,
    )


@admin_bp.get("/users")
@require_admin
def users():
    query = (request.args.get("q") or "").strip()
    per_page = 50
    try:
        page = max(1, int(request.args.get("page", "1")))
    except ValueError:
        page = 1
    total = db.count_users(query or None)
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, pages)
    offset = (page - 1) * per_page
    return render_template(
        "admin/users.html",
        users=db.list_users(limit=per_page, offset=offset, query=query or None),
        coin_name=COIN_NAME,
        query=query,
        page=page,
        pages=pages,
        total=total,
        has_prev=page > 1,
        has_next=page < pages,
    )


@admin_bp.get("/users/<int:telegram_id>")
@require_admin
def user_detail(telegram_id: int):
    return render_template(
        "admin/user_detail.html",
        user=db.get_user(telegram_id),
        games=db.recent_games(limit=100, telegram_id=telegram_id),
        history=db.player_history(telegram_id, limit=100),
        payments=db.recent_payments(limit=50, telegram_id=telegram_id),
        coin_name=COIN_NAME,
    )


@admin_bp.post("/users/<int:telegram_id>/balance")
@require_admin
def user_balance_adjust(telegram_id: int):
    try:
        amount = int(request.form.get("amount", "0"))
        reason = request.form.get("reason", "").strip() or "admin_adjustment"
        result = db.adjust_balance(
            telegram_id=telegram_id,
            amount=amount,
            reason="admin_adjustment",
            meta={"admin_id": settings.admin_id, "note": reason},
        )
    except (ValueError, BalanceError) as exc:
        flash(f"Balance adjustment failed: {exc}", "error")
    else:
        flash(
            f"Balance adjusted by {result['amount']} {COIN_NAME}. New balance: {result['balance_after']} {COIN_NAME}.",
            "success",
        )
    return redirect(url_for("admin.user_detail", telegram_id=telegram_id))


def _entitlement_action(telegram_id: int, kind: str, default_days: int) -> None:
    action = request.form.get("action", "grant")
    label = "Premium" if kind == "premium" else "Season Pass"
    try:
        days = None if action == "revoke" else max(1, int(request.form.get("days", str(default_days)) or default_days))
        user = db.admin_set_entitlement(telegram_id, kind, days, admin_id=settings.admin_id)
    except (ValueError, BalanceError) as exc:
        flash(f"{label} update failed: {exc}", "error")
        return
    if user is None:
        flash("User not found.", "error")
        return
    if days is None:
        flash(f"{label} revoked.", "success")
    else:
        until = user.get("premium_until" if kind == "premium" else "season_pass_until")
        flash(f"{label} granted for {days} days (until {until}).", "success")


@admin_bp.post("/users/<int:telegram_id>/premium")
@require_admin
def user_premium(telegram_id: int):
    _entitlement_action(telegram_id, "premium", default_days=30)
    return redirect(url_for("admin.user_detail", telegram_id=telegram_id))


@admin_bp.post("/users/<int:telegram_id>/season")
@require_admin
def user_season(telegram_id: int):
    _entitlement_action(telegram_id, "season_pass", default_days=60)
    return redirect(url_for("admin.user_detail", telegram_id=telegram_id))


@admin_bp.post("/users/<int:telegram_id>/luck")
@require_admin
def user_luck(telegram_id: int):
    try:
        user = db.admin_set_luck_factor(
            telegram_id,
            request.form.get("luck_factor", "1"),
            admin_id=settings.admin_id,
        )
    except BalanceError as exc:
        flash(f"Luck update failed: {exc}", "error")
        return redirect(url_for("admin.user_detail", telegram_id=telegram_id))
    if user is None:
        flash("User not found.", "error")
    else:
        flash(f"Luck factor set to {user.get('luck_factor'):.2f}.", "success")
    return redirect(url_for("admin.user_detail", telegram_id=telegram_id))


@admin_bp.post("/users/<int:telegram_id>/ban")
@require_admin
def user_ban(telegram_id: int):
    reason = request.form.get("reason", "").strip()
    if telegram_id == settings.admin_id:
        flash("Admin account cannot be banned from the admin panel.", "error")
        return redirect(url_for("admin.user_detail", telegram_id=telegram_id))
    user = db.set_user_ban(telegram_id, True, reason=reason, admin_id=settings.admin_id)
    flash("User blocked." if user else "User not found.", "success" if user else "error")
    return redirect(url_for("admin.user_detail", telegram_id=telegram_id))


@admin_bp.post("/users/<int:telegram_id>/unban")
@require_admin
def user_unban(telegram_id: int):
    user = db.set_user_ban(telegram_id, False, admin_id=settings.admin_id)
    flash("User unblocked." if user else "User not found.", "success" if user else "error")
    return redirect(url_for("admin.user_detail", telegram_id=telegram_id))


@admin_bp.get("/payments")
@require_admin
def payments():
    return render_template("admin/payments.html", payments=db.recent_payments(limit=200))


@admin_bp.post("/payments/<path:charge_id>/refund")
@require_admin
def refund_payment(charge_id: str):
    payment = db.get_payment(charge_id)
    if payment is None:
        flash("Payment not found.", "error")
        return redirect(url_for("admin.payments"))
    if payment.get("refunded_at"):
        flash("Payment is already marked as refunded.", "error")
        return redirect(url_for("admin.payments"))

    try:
        result = runtime.submit(
            bot.refund_star_payment(
                user_id=int(payment["telegram_id"]),
                telegram_payment_charge_id=charge_id,
            )
        ).result(timeout=30)
    except Exception as exc:
        flash(f"Telegram refund failed: {exc}", "error")
        return redirect(url_for("admin.payments"))

    if not result:
        flash("Telegram returned false for refund.", "error")
        return redirect(url_for("admin.payments"))

    db.mark_payment_refunded(
        charge_id,
        admin_id=settings.admin_id,
        meta={"source": "admin_panel"},
    )
    flash("Stars payment refunded and marked in DB.", "success")
    return redirect(url_for("admin.payments"))


@admin_bp.get("/broadcast")
@require_admin
def broadcast_form():
    return render_template("admin/broadcast.html", jobs=_broadcast_jobs_snapshot())


@admin_bp.post("/broadcast")
@require_admin
def broadcast_send():
    text = request.form.get("text", "").strip()
    photo_url = request.form.get("photo_url", "").strip()
    button_text = request.form.get("button_text", "").strip()
    button_url = request.form.get("button_url", "").strip()

    if not text and not photo_url:
        flash("Text or photo URL is required.", "error")
        return redirect(url_for("admin.broadcast_form"))

    user_ids = db.all_telegram_ids()
    job = {
        "id": secrets.token_hex(4),
        "status": "running",
        "created_at": db.now(),
        "total": len(user_ids),
        "sent": 0,
        "failed": 0,
        "preview": text[:80] if text else photo_url[:80],
    }
    with _broadcast_jobs_guard:
        _broadcast_jobs.appendleft(job)

    future = runtime.submit(
        send_broadcast(
            bot=bot,
            user_ids=user_ids,
            text=text,
            photo_url=photo_url,
            button_text=button_text,
            button_url=button_url,
        )
    )
    future.add_done_callback(lambda completed_future: _finish_broadcast_job(job, completed_future))
    flash(f"Broadcast started for {len(user_ids)} users. Refresh this page to see completion status.", "success")
    return redirect(url_for("admin.broadcast_form"))
