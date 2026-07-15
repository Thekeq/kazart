from __future__ import annotations

from app import create_app
from config import settings
from loader import start_polling_in_background


app = create_app()


if __name__ == "__main__":
    if settings.bot_mode == "polling":
        start_polling_in_background()
        print("Telegram bot mode: polling")
    else:
        print("Telegram bot mode: webhook")

    print(f"WebApp: http://127.0.0.1:{settings.port}/app")
    print(f"Admin:  http://127.0.0.1:{settings.port}/admin")
    app.run(
        host=settings.host,
        port=settings.port,
        debug=settings.debug,
        threaded=True,
        use_reloader=False,
    )
