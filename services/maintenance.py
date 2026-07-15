from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


_LOGGING_CONFIGURED = False


def configure_logging(settings: Any) -> None:
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if not root.handlers:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)

    log_file = getattr(settings, "log_file", None)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        existing_files = {
            Path(getattr(handler, "baseFilename", "")).resolve()
            for handler in root.handlers
            if getattr(handler, "baseFilename", None)
        }
        if log_path.resolve() not in existing_files:
            file_handler = RotatingFileHandler(
                log_path,
                maxBytes=5 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)

    _LOGGING_CONFIGURED = True


def backup_sqlite_database(db_path: str | Path, backup_dir: str | Path, keep: int = 10) -> Path | None:
    if str(db_path) == ":memory:":
        return None

    source = Path(db_path)
    if not source.exists():
        return None

    target_dir = Path(backup_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = target_dir / f"{source.stem}-{stamp}.db"

    with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
        src.backup(dst)

    logging.getLogger(__name__).info("SQLite backup created: %s", target)
    _prune_old_backups(target_dir, source.stem, keep)
    return target


def _prune_old_backups(backup_dir: Path, db_stem: str, keep: int) -> None:
    if keep <= 0:
        return

    root = backup_dir.resolve()
    backups = sorted(
        backup_dir.glob(f"{db_stem}-*.db"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for old_backup in backups[keep:]:
        if old_backup.resolve().parent == root:
            old_backup.unlink(missing_ok=True)
