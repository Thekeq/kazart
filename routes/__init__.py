from __future__ import annotations

from flask import Flask


def register_blueprints(app: Flask) -> None:
    from routes.admin import admin_bp
    from routes.api import api_bp
    from routes.telegram import telegram_bp
    from routes.web import web_bp

    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(telegram_bp)
