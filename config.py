from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _int_env(name: str, default: int = 0) -> int:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return int(value)


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _path_env(name: str, default: str | Path, allow_none: bool = False) -> Path | None:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        if allow_none:
            return None
        value = Path(default)
    elif allow_none and raw.strip().lower() in {"0", "false", "none", "off"}:
        return None
    else:
        value = Path(raw.strip())
    return value if value.is_absolute() else BASE_DIR / value


def _database_env(name: str, default: str | Path) -> str | Path:
    raw = os.getenv(name)
    if raw is not None and raw.strip() == ":memory:":
        return ":memory:"
    path = _path_env(name, default)
    if path is None:
        raise RuntimeError(f"{name} cannot be disabled")
    return path


def _is_local_url(value: str) -> bool:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    return host in {"", "localhost", "127.0.0.1", "::1"}


def _is_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    return lowered in {
        "",
        "change-this-secret",
        "change-this-flask-secret",
        "change-this-password",
        "replace-me",
    }


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_id: int
    coin_name: str
    bot_mode: str
    database_path: str | Path
    public_webapp_url: str
    public_base_url: str
    webhook_secret_token: str
    admin_password: str
    flask_secret_key: str
    host: str
    port: int
    debug: bool
    log_file: Path | None
    backup_dir: Path
    backup_on_start: bool
    backup_keep: int
    drop_pending_updates: bool
    support_url: str
    support_username: str
    support_email: str
    support_text: str
    require_legal_acceptance: bool
    game_action_limit: int
    game_action_window_seconds: int
    state_poll_limit: int
    state_poll_window_seconds: int
    shop_invoice_limit: int
    shop_invoice_window_seconds: int
    bonus_claim_limit: int
    bonus_claim_window_seconds: int
    min_bet: int
    max_bet: int
    session_cookie_secure: bool
    trust_proxy_headers: bool
    init_data_max_age_seconds: int = 86400


def load_settings() -> Settings:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError("BOT_TOKEN is not set in .env")

    admin_id = _int_env("ADMIN_ID")
    if not admin_id:
        raise RuntimeError("ADMIN_ID is not set in .env")

    database_path = _database_env("DB_FILE", BASE_DIR / "data.db")

    public_base_url = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
    public_webapp_url = os.getenv("PUBLIC_WEBAPP_URL", f"{public_base_url}/app").strip()
    bot_mode = os.getenv("BOT_MODE", "polling").strip().lower()
    if bot_mode not in {"polling", "webhook"}:
        raise RuntimeError("BOT_MODE must be 'polling' or 'webhook'")
    production_like = bot_mode == "webhook" or not _is_local_url(public_base_url)
    webhook_secret_token = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
    if bot_mode == "webhook" and _is_placeholder(webhook_secret_token):
        raise RuntimeError("TELEGRAM_WEBHOOK_SECRET must be set to a strong non-placeholder value in webhook mode")

    admin_password = os.getenv("ADMIN_PASSWORD", "").strip()
    if production_like and _is_placeholder(admin_password):
        raise RuntimeError("ADMIN_PASSWORD must be set to a strong non-placeholder value for public deployments")

    flask_secret_key = os.getenv("FLASK_SECRET_KEY", "").strip()
    if production_like and _is_placeholder(flask_secret_key):
        raise RuntimeError("FLASK_SECRET_KEY must be set to a strong non-placeholder value for public deployments")
    if production_like and len(flask_secret_key) < 16:
        raise RuntimeError(
            "FLASK_SECRET_KEY is too short for a public deployment (need 16+ random characters). "
            "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
        )
    if not flask_secret_key:
        flask_secret_key = "dev-only-change-this-flask-secret"

    debug = _bool_env("FLASK_DEBUG", False)
    if debug and production_like:
        raise RuntimeError("FLASK_DEBUG must be false for public deployments")

    min_bet = max(1, _int_env("MIN_BET", 1))
    max_bet = max(min_bet, _int_env("MAX_BET", 100000))

    return Settings(
        bot_token=bot_token,
        admin_id=admin_id,
        coin_name=os.getenv("COIN_NAME", "coins").strip() or "coins",
        bot_mode=bot_mode,
        database_path=database_path,
        public_webapp_url=public_webapp_url,
        public_base_url=public_base_url,
        webhook_secret_token=webhook_secret_token,
        admin_password=admin_password,
        flask_secret_key=flask_secret_key,
        host=os.getenv("HOST", "0.0.0.0"),
        port=_int_env("PORT", 5000),
        debug=debug,
        log_file=_path_env("LOG_FILE", "logs/app.log", allow_none=True),
        backup_dir=_path_env("BACKUP_DIR", "backups"),
        backup_on_start=_bool_env("BACKUP_ON_START", True),
        backup_keep=_int_env("BACKUP_KEEP", 10),
        drop_pending_updates=_bool_env("DROP_PENDING_UPDATES", True),
        support_url=os.getenv("SUPPORT_URL", f"{public_base_url}/support").strip(),
        support_username=os.getenv("SUPPORT_USERNAME", "").strip().lstrip("@"),
        support_email=os.getenv("SUPPORT_EMAIL", "").strip(),
        support_text=os.getenv("SUPPORT_TEXT", "").strip(),
        require_legal_acceptance=_bool_env("REQUIRE_LEGAL_ACCEPTANCE", True),
        game_action_limit=_int_env("GAME_ACTION_LIMIT", 12),
        game_action_window_seconds=_int_env("GAME_ACTION_WINDOW_SECONDS", 10),
        state_poll_limit=_int_env("STATE_POLL_LIMIT", 90),
        state_poll_window_seconds=_int_env("STATE_POLL_WINDOW_SECONDS", 60),
        shop_invoice_limit=_int_env("SHOP_INVOICE_LIMIT", 3),
        shop_invoice_window_seconds=_int_env("SHOP_INVOICE_WINDOW_SECONDS", 300),
        bonus_claim_limit=_int_env("BONUS_CLAIM_LIMIT", 5),
        bonus_claim_window_seconds=_int_env("BONUS_CLAIM_WINDOW_SECONDS", 300),
        min_bet=min_bet,
        max_bet=max_bet,
        session_cookie_secure=_bool_env("SESSION_COOKIE_SECURE", public_base_url.startswith("https://")),
        trust_proxy_headers=_bool_env("TRUST_PROXY_HEADERS", False),
        init_data_max_age_seconds=_int_env("INIT_DATA_MAX_AGE_SECONDS", 86400),
    )


settings = load_settings()
