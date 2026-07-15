from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl


class TelegramAuthError(ValueError):
    pass


@dataclass(frozen=True)
class WebAppAuth:
    user: dict[str, Any]
    auth_date: int
    raw: dict[str, str]


def validate_init_data(init_data: str, bot_token: str, max_age_seconds: int = 86400) -> WebAppAuth:
    if not init_data:
        raise TelegramAuthError("Missing Telegram initData")

    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    except ValueError as exc:
        raise TelegramAuthError("Malformed initData") from exc
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise TelegramAuthError("Missing initData hash")

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise TelegramAuthError("Bad initData signature")

    auth_date_raw = pairs.get("auth_date")
    if not auth_date_raw or not auth_date_raw.isdigit():
        raise TelegramAuthError("Missing auth_date")

    auth_date = int(auth_date_raw)
    if max_age_seconds > 0 and int(time.time()) - auth_date > max_age_seconds:
        raise TelegramAuthError("initData expired")

    if "user" not in pairs:
        raise TelegramAuthError("Missing Telegram user")

    try:
        user = json.loads(pairs["user"])
    except json.JSONDecodeError as exc:
        raise TelegramAuthError("Bad Telegram user payload") from exc

    if "id" not in user:
        raise TelegramAuthError("Telegram user id is missing")
    try:
        int(user["id"])
    except (TypeError, ValueError) as exc:
        raise TelegramAuthError("Bad Telegram user id") from exc

    return WebAppAuth(user=user, auth_date=auth_date, raw=pairs)
