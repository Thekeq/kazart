from __future__ import annotations

from pathlib import Path

from flask import Blueprint, redirect, render_template, url_for

from config import settings
from services.games import PLINKO_RISK_TABLES, UPGRADER_MULTIPLIERS


web_bp = Blueprint("web", __name__)
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def _asset_version() -> str:
    try:
        stamps = [
            int((_STATIC_DIR / "js" / "webapp.js").stat().st_mtime),
            int((_STATIC_DIR / "css" / "webapp.css").stat().st_mtime),
        ]
        return str(max(stamps))
    except OSError:
        return "1"


ASSET_VERSION = _asset_version()


@web_bp.get("/")
def index():
    return redirect(url_for("web.webapp"))


@web_bp.get("/app")
def webapp():
    return render_template(
        "webapp.html",
        coin_name=settings.coin_name,
        upgrader_multipliers=UPGRADER_MULTIPLIERS,
        plinko_risks=PLINKO_RISK_TABLES,
        plinko_slots=PLINKO_RISK_TABLES["medium"]["multipliers"],
        public_webapp_url=settings.public_webapp_url,
        asset_version=ASSET_VERSION,
    )


@web_bp.get("/terms")
def terms():
    return render_template("legal.html", page="terms")


@web_bp.get("/privacy")
def privacy():
    return render_template("legal.html", page="privacy")


@web_bp.get("/support")
@web_bp.get("/paysupport")
def support():
    return render_template("support.html", settings=settings)
