from __future__ import annotations

from aiogram import Bot
from aiogram.types import LabeledPrice


DAILY_BONUS_RENEW_STARS = 25
DAILY_BONUS_RENEW_KIND = "daily_bonus_renew"
SHOP_ITEMS = (
    {
        "kind": DAILY_BONUS_RENEW_KIND,
        "stars": DAILY_BONUS_RENEW_STARS,
        "title": "Renew daily bonus",
        "description": "Reset the 24h daily bonus timer. This does not buy coins directly.",
        "category": "utility",
    },
    {
        "kind": "cosmetic_neon_theme",
        "stars": 15,
        "title": "Neon table theme",
        "description": "Cosmetic Mini App theme. No gameplay advantage.",
        "category": "cosmetic",
    },
    {
        "kind": "cosmetic_gold_ball",
        "stars": 15,
        "title": "Gold Plinko ball",
        "description": "Cosmetic Plinko ball skin. No gameplay advantage.",
        "category": "cosmetic",
    },
    {
        "kind": "premium_30d",
        "stars": 99,
        "title": "Premium 30 days",
        "description": "Profile badge, cosmetics and convenience features. No gameplay advantage.",
        "category": "premium",
    },
    {
        "kind": "season_pass",
        "stars": 149,
        "title": "Season pass",
        "description": "Premium season reward track with cosmetic rewards. No gameplay advantage.",
        "category": "premium",
    },
)


def shop_items() -> list[dict]:
    return [dict(item) for item in SHOP_ITEMS]


def shop_item(kind: str) -> dict | None:
    return next((dict(row) for row in SHOP_ITEMS if row["kind"] == kind), None)


def shop_payload(kind: str, stars: int) -> str:
    item = shop_item(kind)
    if item is None or int(stars) != int(item["stars"]):
        raise ValueError("Unknown shop item")
    return f"{item['kind']}:{item['stars']}"


def parse_shop_payload(payload: str) -> tuple[str, int]:
    parts = payload.split(":")
    if len(parts) != 2:
        raise ValueError("Bad payment payload")
    item = shop_item(parts[0])
    if item is None:
        raise ValueError("Bad payment payload")
    try:
        stars = int(parts[1])
    except ValueError as exc:
        raise ValueError("Bad payment payload") from exc
    if stars != int(item["stars"]):
        raise ValueError("Bad payment package")
    return item["kind"], stars


async def create_stars_invoice_link(bot: Bot, kind: str) -> dict:
    item = next((row for row in shop_items() if row["kind"] == kind), None)
    if item is None:
        raise ValueError("Unknown shop item")

    link = await bot.create_invoice_link(
        title=item["title"],
        description=item["description"],
        payload=shop_payload(item["kind"], item["stars"]),
        currency="XTR",
        prices=[LabeledPrice(label=item["title"], amount=item["stars"])],
        provider_token="",
    )
    return {**item, "invoice_link": link}
