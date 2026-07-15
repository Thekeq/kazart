from __future__ import annotations

from app import create_app
from config import settings
from loader import start_polling_in_background


app = create_app()

if settings.bot_mode == "polling":
    start_polling_in_background()
