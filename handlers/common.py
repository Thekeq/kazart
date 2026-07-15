from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, PreCheckoutQuery, WebAppInfo

from config import settings
from loader import ADMIN_ID, COIN_NAME, db
from services.shop import DAILY_BONUS_RENEW_KIND, parse_shop_payload


router = Router(name="common")
logger = logging.getLogger(__name__)


def miniapp_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Open Mini App", web_app=WebAppInfo(url=settings.public_webapp_url))]
        ]
    )


def support_text(payment: bool = False) -> str:
    lines = [
        "KAZart payment support" if payment else "KAZart support",
        "",
        "KAZart is 18+ entertainment with virtual coins only. Coins have no cash value and cannot be withdrawn, sold, transferred, exchanged for prizes, or redeemed for goods.",
    ]
    if payment:
        lines.extend(
            [
                "",
                "Current Stars items: daily bonus renewal, cosmetics, Premium, and Season Pass. These are digital app features and do not buy coins directly.",
                "For payment help or refund review, include your Telegram user id, payment time, and charge id if Telegram shows it.",
            ]
        )
    if settings.support_text:
        lines.extend(["", settings.support_text])
    if settings.support_username:
        lines.append(f"Telegram: @{settings.support_username}")
    if settings.support_email:
        lines.append(f"Email: {settings.support_email}")
    if settings.support_url:
        lines.append(f"Support page: {settings.support_url}")
    if not any((settings.support_text, settings.support_username, settings.support_email, settings.support_url)):
        lines.append("Contact the bot administrator for help.")
    return "\n".join(lines)


@router.message(Command("app"))
@router.message(Command("games"))
async def open_app(message: Message) -> None:
    db.ensure_user(message.from_user, is_admin=message.from_user.id == ADMIN_ID)
    await message.answer("All games are inside the Mini App.", reply_markup=miniapp_keyboard())


@router.message(Command("balance"))
async def balance(message: Message) -> None:
    user = db.ensure_user(message.from_user, is_admin=message.from_user.id == ADMIN_ID)
    await message.answer(f"Balance: <b>{user['balance']} {COIN_NAME}</b>", reply_markup=miniapp_keyboard())


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    db.ensure_user(message.from_user, is_admin=message.from_user.id == ADMIN_ID)
    await message.answer(
        "KAZart is an 18+ entertainment Mini App with virtual coins only.\n"
        "No cash out, no prizes, no real-money winnings.\n\n"
        "Commands:\n"
        "/app - open Mini App\n"
        "/balance - show virtual balance\n"
        "/terms - Terms of Use\n"
        "/privacy - Privacy Policy\n"
        "/support - support contacts\n"
        "/paysupport - Stars payment support",
        reply_markup=miniapp_keyboard(),
    )


@router.message(Command("terms"))
async def terms_command(message: Message) -> None:
    await message.answer(
        f"Terms of Use: {settings.public_base_url}/terms\n\n"
        "18+ only. Virtual coins have no cash value and cannot be withdrawn, sold, transferred, exchanged for prizes, or redeemed for goods.",
        reply_markup=miniapp_keyboard(),
        parse_mode=None,
    )


@router.message(Command("privacy"))
async def privacy_command(message: Message) -> None:
    await message.answer(f"Privacy Policy: {settings.public_base_url}/privacy", parse_mode=None)


@router.message(Command("support"))
async def support_command(message: Message) -> None:
    await message.answer(support_text(), parse_mode=None, reply_markup=miniapp_keyboard())


@router.message(Command("paysupport"))
async def payment_support_command(message: Message) -> None:
    await message.answer(support_text(payment=True), parse_mode=None, reply_markup=miniapp_keyboard())


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    try:
        parse_shop_payload(query.invoice_payload)
    except ValueError as exc:
        await query.answer(ok=False, error_message=str(exc))
        return
    try:
        user = db.ensure_user(query.from_user, is_admin=query.from_user.id == ADMIN_ID)
        if int(user.get("is_banned") or 0):
            await query.answer(ok=False, error_message="Account is blocked. Contact support.")
            return
        if settings.require_legal_acceptance and not user.get("legal_accepted_at"):
            await query.answer(ok=False, error_message="Please accept the 18+ virtual-only terms before payment.")
            return
    except Exception:
        logger.exception("Pre-checkout validation failed for user %s", query.from_user.id)
        await query.answer(ok=False, error_message="Temporary error. Please try again in a minute.")
        return
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message) -> None:
    payment = message.successful_payment
    charge_id = payment.telegram_payment_charge_id
    try:
        kind, stars = parse_shop_payload(payment.invoice_payload)
        db.ensure_user(message.from_user, is_admin=message.from_user.id == ADMIN_ID)
        if kind == DAILY_BONUS_RENEW_KIND:
            result = db.renew_daily_bonus(
                telegram_id=message.from_user.id,
                stars=stars,
                payment_charge_id=charge_id,
                payload=payment.invoice_payload,
            )
            text = "Payment complete. Daily bonus timer renewed."
            text += " You can claim it now." if result["applied"] else " It was already applied."
        else:
            result = db.apply_shop_purchase(
                telegram_id=message.from_user.id,
                kind=kind,
                stars=stars,
                payment_charge_id=charge_id,
                payload=payment.invoice_payload,
            )
            text = "Payment complete."
            text += " Applied to your account." if result["applied"] else " It was already applied."
    except Exception:
        # The Stars payment already went through: never fail silently here.
        logger.exception(
            "Failed to apply successful payment (user=%s, charge_id=%s, payload=%r)",
            message.from_user.id,
            charge_id,
            payment.invoice_payload,
        )
        await message.answer(
            "Payment received, but applying it failed. "
            f"Send /paysupport with this charge id: {charge_id}",
            parse_mode=None,
        )
        return
    await message.answer(text, reply_markup=miniapp_keyboard())
