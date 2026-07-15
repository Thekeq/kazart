from __future__ import annotations

from flask import Flask

from config import settings
from loader import register_routers, start_bot_background_tasks, start_game_ticker
from routes import register_blueprints


def create_app() -> Flask:
    register_routers()
    start_bot_background_tasks()
    start_game_ticker()

    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.update(
        SECRET_KEY=settings.flask_secret_key,
        JSON_SORT_KEYS=False,
        MAX_CONTENT_LENGTH=8 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=settings.session_cookie_secure,
    )
    register_blueprints(app)

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response

    return app
