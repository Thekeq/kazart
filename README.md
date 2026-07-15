# KAZart Telegram Mini App

Entertainment Telegram bot with a Flask backend, Telegram WebApp Mini App, SQLite WAL storage, strict Mini App initData validation, and a custom admin panel.

KAZart is 18+ entertainment only. No real-money economy is implemented: coins are virtual, have no cash value, cannot be withdrawn, sold, transferred, redeemed for prizes, or exchanged for goods. `COIN_NAME` from `.env` is used as the virtual currency label.

## Structure

```text
casino/
  app.py                 # Flask application factory
  main.py                # Flask entrypoint
  config.py              # .env settings
  db.py                  # SQLite WAL, schema, migrations, per-user locks
  loader.py              # aiogram bot/dispatcher/db/runtime
  handlers/              # Telegram commands, payments, admin handlers
  routes/                # Flask web, API, admin, webhook routes
  services/              # game logic, initData auth, broadcast sender
  services/maintenance.py # logging and SQLite startup backups
  templates/             # WebApp and admin Jinja templates
  static/                # Mini App CSS/JS
  requirements.txt
```

## Run locally

```bash
pip install -r requirements.txt
python main.py
```

By default `BOT_MODE=polling`, so `python main.py` starts both the Telegram bot polling and the Flask site/admin/API in one process.

Polling deletes pending webhook updates by default before starting. Set `DROP_PENDING_UPDATES=false` only if you intentionally need to process queued updates after downtime.

Open `http://127.0.0.1:5000/app` for layout preview. Game API requests require Telegram `initData`, so real gameplay must be opened from the bot's Mini App button.

Terms, privacy, and support pages are available at `/terms`, `/privacy`, and `/support`.

## Deploy (production)

Do not use `python main.py` (Flask dev server) for a public deployment. Use a WSGI server with **exactly one process/worker** (shared Crash/Roulette rounds and rate limits live in process memory; threads are fine):

```bash
# Linux
gunicorn --workers 1 --threads 8 --bind 0.0.0.0:5000 wsgi:app

# Windows
waitress-serve --listen=0.0.0.0:5000 --threads=8 wsgi:app
```

`wsgi.py` creates the app, starts the game ticker and bot background tasks, and starts Telegram polling when `BOT_MODE=polling`.

Behind a reverse proxy (nginx/Cloudflare) that sets `X-Forwarded-For`, also set `TRUST_PROXY_HEADERS=true` so admin login rate limiting sees real client IPs. Never enable it without a trusted proxy in front.

Startup safety checks refuse to boot a public deployment with `FLASK_DEBUG=true`, a placeholder `ADMIN_PASSWORD`, or a weak/placeholder `FLASK_SECRET_KEY`.

## Public Safety Gates

The backend enforces these rules, not only the frontend modal:

- Mini App initData is validated server-side for every API request.
- Users must accept the 18+ virtual-only terms before game actions, bonus claims, leaderboard access, or Stars invoice creation.
- API abuse limits are applied to game actions, state polling, bonus claims, and Stars invoice creation.
- Referral rewards are delayed until the invited user accepts the 18+ virtual-only terms.
- Banned users are blocked from protected Mini App actions, broadcasts, leaderboards, reminders, and Stars checkout.
- Admin POST actions are protected by CSRF tokens and SameSite session cookies.

## Shop and Retention

Telegram Stars are not used to buy coins. The shop sells only digital app features: `Renew daily bonus`, cosmetics, Premium, and Season Pass. Cosmetics and Premium do not change odds, payouts, or RTP.

Retention systems included:

- Daily bonus streaks.
- Daily quests with virtual rewards.
- Season XP/level display.
- Cosmetic inventory and active cosmetic selection.

Roulette supports shared rooms with bets on a single number, red/black, 1-18, 19-36, and dozens.

Payment support:

- `/paysupport` is implemented in the bot.
- `/support` is available as a public web page.
- `/admin/payments` shows recent Stars payments and can call Telegram `refund_star_payment`.

Configure support contacts:

```text
SUPPORT_URL=https://your-domain.example/support
SUPPORT_USERNAME=your_support_username
SUPPORT_EMAIL=support@example.com
SUPPORT_TEXT="Support responds within 48 hours."
```

Also set the privacy policy URL in BotFather to `https://your-domain.example/privacy`.

## Rate Limits

Defaults:

```text
GAME_ACTION_LIMIT=12
GAME_ACTION_WINDOW_SECONDS=10
STATE_POLL_LIMIT=90
STATE_POLL_WINDOW_SECONDS=60
SHOP_INVOICE_LIMIT=3
SHOP_INVOICE_WINDOW_SECONDS=300
BONUS_CLAIM_LIMIT=5
BONUS_CLAIM_WINDOW_SECONDS=300
REQUIRE_LEGAL_ACCEPTANCE=true
MIN_BET=1
MAX_BET=100000
```

## Logging and Backups

Optional production-safety settings:

```text
LOG_FILE=logs/app.log
DB_FILE=data.db
BACKUP_DIR=backups
BACKUP_ON_START=true
BACKUP_KEEP=10
```

When `BACKUP_ON_START=true`, the app creates a SQLite backup before `DataBase` runs migrations. Logs rotate at 5 MB with 5 retained files. `DB_FILE=:memory:` is supported for tests and smoke checks; startup backups are skipped for in-memory databases.

## Telegram webhook

Webhook is optional for production. To use it, expose Flask through HTTPS and set:

```text
BOT_MODE=webhook
PUBLIC_BASE_URL=https://your-domain.example
PUBLIC_WEBAPP_URL=https://your-domain.example/app
TELEGRAM_WEBHOOK_SECRET=change-this-secret
```

Then set the webhook in Telegram:

```bash
curl "https://api.telegram.org/bot$BOT_TOKEN/setWebhook" \
  -d "url=$PUBLIC_BASE_URL/telegram/webhook" \
  -d "secret_token=$TELEGRAM_WEBHOOK_SECRET"
```

## Admin

Set `ADMIN_PASSWORD` in `.env`, restart Flask, then open `/admin`. Admin stats include user count, legal acceptance count, blocked users, total virtual balance, recent game logs, Stars payment logs, user details, refunds, and background broadcast jobs with optional photo URL and button.

User detail pages include manual balance adjustment, block/unblock actions, Stars payments, game logs, and a combined player history. Balance adjustments are virtual-only admin operations and cannot create cash value.

For HTTPS production:

```text
SESSION_COOKIE_SECURE=true
FLASK_DEBUG=false
```

For local HTTP development, set `SESSION_COOKIE_SECURE=false` if admin login does not keep the session.

## Pre-Launch Checklist

- `PUBLIC_BASE_URL` and `PUBLIC_WEBAPP_URL` point to the final HTTPS domain.
- BotFather Mini App URL points to `/app`.
- BotFather privacy policy URL points to `/privacy`.
- `/support` and `/paysupport` work and contain real support contact details (`SUPPORT_URL` is not a placeholder).
- `ADMIN_PASSWORD`, `FLASK_SECRET_KEY`, and `TELEGRAM_WEBHOOK_SECRET` are long random secrets.
- `FLASK_DEBUG=false` (enforced at startup for public URLs).
- The app runs under a WSGI server with a single worker process (see Deploy). Multiple workers would split the in-memory Crash/Roulette rooms and rate limits.
- `TRUST_PROXY_HEADERS=true` only if a trusted reverse proxy sets `X-Forwarded-For`.
- `BACKUP_ON_START=true` and backup restore was tested once.
- Run tests once: `python -m unittest discover -s tests -v`.
