from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_START_BALANCE = 1000
DAILY_BONUS_AMOUNT = 1000
DAILY_BONUS_STREAK_STEP = 150
DAILY_BONUS_STREAK_CAP_DAY = 7
REFERRAL_REWARD_AMOUNT = 1000
WEEKLY_REWARD_AMOUNTS = (25000, 15000, 10000)


def daily_bonus_amount(streak_count: int) -> int:
    """Bonus for the day the streak reaches ``streak_count`` (1-based).

    Day 1 = base 1000, growing by 150 up to day 7 (1900), then flat.
    """
    steps = min(max(int(streak_count) - 1, 0), DAILY_BONUS_STREAK_CAP_DAY - 1)
    return DAILY_BONUS_AMOUNT + steps * DAILY_BONUS_STREAK_STEP
QUEST_REWARDS = {
    "daily_bonus": 150,
    "play_5": 250,
    "win_3": 250,
    "try_3_games": 300,
    "big_win": 400,
    "crash_cashout": 200,
    "roulette_room": 200,
    "volume_1000": 300,
    "invite_1": 500,
}

ACHIEVEMENTS: tuple[dict[str, Any], ...] = (
    {"id": "first_win", "target": 1, "reward": 200},
    {"id": "games_50", "target": 50, "reward": 300},
    {"id": "games_250", "target": 250, "reward": 800},
    {"id": "games_1000", "target": 1000, "reward": 2000},
    {"id": "wins_100", "target": 100, "reward": 700},
    {"id": "big_x10", "target": 1, "reward": 500},
    {"id": "streak_7", "target": 7, "reward": 600},
    {"id": "streak_30", "target": 30, "reward": 2500},
    {"id": "invite_3", "target": 3, "reward": 900},
    {"id": "invite_10", "target": 10, "reward": 3000},
    {"id": "all_games", "target": 5, "reward": 400},
    {"id": "total_bet_100k", "target": 100_000, "reward": 1500},
)

SEASON_KEY = "s1"
SEASON_MAX_LEVEL = 50
SEASON_LEVEL_XP = 250


def season_level_rewards(level: int) -> dict[str, int]:
    return {"free": 100 + level * 50, "premium": 200 + level * 100}


class BalanceError(ValueError):
    pass


class DataBase:
    def __init__(self, db_file: str | Path):
        self._in_memory = str(db_file) == ":memory:"
        self._memory_keeper: sqlite3.Connection | None = None
        if self._in_memory:
            self.db_file: str | Path = f"file:casino-{id(self)}?mode=memory&cache=shared"
        else:
            self.db_file = Path(db_file)
            self.db_file.parent.mkdir(parents=True, exist_ok=True)
        self._locks_guard = threading.Lock()
        self._user_locks: dict[int, threading.RLock] = {}
        if self._in_memory:
            self._memory_keeper = self.connect()
        self._migrate()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_file, timeout=15, isolation_level=None, uri=self._in_memory)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=MEMORY;" if self._in_memory else "PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA busy_timeout=15000;")
        return conn

    def close(self) -> None:
        if self._memory_keeper is not None:
            self._memory_keeper.close()
            self._memory_keeper = None

    @contextmanager
    def connection(self) -> Iterable[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Iterable[sqlite3.Connection]:
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            try:
                yield conn
            except Exception:
                conn.rollback()
                raise
            else:
                conn.commit()

    @contextmanager
    def user_lock(self, telegram_id: int) -> Iterable[None]:
        lock = self._get_user_lock(telegram_id)
        with lock:
            yield

    def _get_user_lock(self, telegram_id: int) -> threading.RLock:
        with self._locks_guard:
            lock = self._user_locks.get(telegram_id)
            if lock is None:
                lock = threading.RLock()
                self._user_locks[telegram_id] = lock
            return lock

    def _migrate(self) -> None:
        with self.transaction() as conn:
            user_columns = self._columns(conn, "users")
            if not user_columns:
                conn.executescript(
                    """
                    CREATE TABLE users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        telegram_id INTEGER NOT NULL UNIQUE,
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        balance INTEGER NOT NULL DEFAULT 1000,
                        is_admin INTEGER NOT NULL DEFAULT 0,
                        is_banned INTEGER NOT NULL DEFAULT 0,
                        ban_reason TEXT,
                        banned_at TEXT,
                        referred_by INTEGER,
                        referral_count INTEGER NOT NULL DEFAULT 0,
                        referral_rewarded_at TEXT,
                        last_daily_bonus_at TEXT,
                        daily_reminder_sent_at TEXT,
                        bonus_notify_enabled INTEGER NOT NULL DEFAULT 1,
                        upgrader_multiplier REAL NOT NULL DEFAULT 1.5,
                        upgrader_chance REAL NOT NULL DEFAULT 64.0,
                        luck_factor REAL NOT NULL DEFAULT 1.0,
                        daily_streak_count INTEGER NOT NULL DEFAULT 0,
                        best_daily_streak INTEGER NOT NULL DEFAULT 0,
                        quest_notify_period TEXT,
                        premium_until TEXT,
                        season_pass_until TEXT,
                        active_cosmetic TEXT,
                        legal_accepted_at TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        last_seen_at TEXT NOT NULL
                    );
                    """
                )
            else:
                self._add_column(conn, user_columns, "users", "telegram_id", "INTEGER")
                self._add_column(conn, user_columns, "users", "username", "TEXT")
                self._add_column(conn, user_columns, "users", "first_name", "TEXT")
                self._add_column(conn, user_columns, "users", "last_name", "TEXT")
                self._add_column(conn, user_columns, "users", "balance", "INTEGER NOT NULL DEFAULT 1000")
                self._add_column(conn, user_columns, "users", "is_admin", "INTEGER NOT NULL DEFAULT 0")
                self._add_column(conn, user_columns, "users", "is_banned", "INTEGER NOT NULL DEFAULT 0")
                self._add_column(conn, user_columns, "users", "ban_reason", "TEXT")
                self._add_column(conn, user_columns, "users", "banned_at", "TEXT")
                self._add_column(conn, user_columns, "users", "referred_by", "INTEGER")
                self._add_column(conn, user_columns, "users", "referral_count", "INTEGER NOT NULL DEFAULT 0")
                had_referral_rewarded_at = "referral_rewarded_at" in user_columns
                self._add_column(conn, user_columns, "users", "referral_rewarded_at", "TEXT")
                self._add_column(conn, user_columns, "users", "last_daily_bonus_at", "TEXT")
                self._add_column(conn, user_columns, "users", "daily_reminder_sent_at", "TEXT")
                self._add_column(conn, user_columns, "users", "bonus_notify_enabled", "INTEGER NOT NULL DEFAULT 1")
                self._add_column(conn, user_columns, "users", "upgrader_multiplier", "REAL NOT NULL DEFAULT 1.5")
                self._add_column(conn, user_columns, "users", "upgrader_chance", "REAL NOT NULL DEFAULT 64.0")
                self._add_column(conn, user_columns, "users", "luck_factor", "REAL NOT NULL DEFAULT 1.0")
                self._add_column(conn, user_columns, "users", "daily_streak_count", "INTEGER NOT NULL DEFAULT 0")
                self._add_column(conn, user_columns, "users", "best_daily_streak", "INTEGER NOT NULL DEFAULT 0")
                self._add_column(conn, user_columns, "users", "quest_notify_period", "TEXT")
                self._add_column(conn, user_columns, "users", "premium_until", "TEXT")
                self._add_column(conn, user_columns, "users", "season_pass_until", "TEXT")
                self._add_column(conn, user_columns, "users", "active_cosmetic", "TEXT")
                self._add_column(conn, user_columns, "users", "legal_accepted_at", "TEXT")
                self._add_column(conn, user_columns, "users", "created_at", "TEXT")
                self._add_column(conn, user_columns, "users", "updated_at", "TEXT")
                self._add_column(conn, user_columns, "users", "last_seen_at", "TEXT")
                now = self.now()
                if "user_id" in user_columns:
                    conn.execute("UPDATE users SET telegram_id = COALESCE(telegram_id, user_id)")
                conn.execute("UPDATE users SET created_at = COALESCE(created_at, ?)", (now,))
                conn.execute("UPDATE users SET updated_at = COALESCE(updated_at, ?)", (now,))
                conn.execute("UPDATE users SET last_seen_at = COALESCE(last_seen_at, ?)", (now,))
                if not had_referral_rewarded_at:
                    conn.execute(
                        """
                        UPDATE users
                        SET referral_rewarded_at = COALESCE(created_at, ?)
                        WHERE referred_by IS NOT NULL
                        """,
                        (now,),
                    )

            conn.executescript(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_users_telegram_id
                    ON users (telegram_id);

                CREATE TABLE IF NOT EXISTS games_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL,
                    game TEXT NOT NULL,
                    bet INTEGER NOT NULL,
                    multiplier REAL NOT NULL,
                    outcome TEXT NOT NULL,
                    win_amount INTEGER NOT NULL DEFAULT 0,
                    balance_before INTEGER NOT NULL,
                    balance_after INTEGER NOT NULL,
                    meta_json TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
                );

                CREATE INDEX IF NOT EXISTS idx_games_log_user_created
                    ON games_log (telegram_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_games_log_created
                    ON games_log (created_at DESC);

                CREATE TABLE IF NOT EXISTS balance_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL,
                    amount INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    balance_before INTEGER NOT NULL,
                    balance_after INTEGER NOT NULL,
                    meta_json TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
                );

                CREATE INDEX IF NOT EXISTS idx_balance_events_user_created
                    ON balance_events (telegram_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS runtime_state (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS telegram_payments (
                    telegram_payment_charge_id TEXT PRIMARY KEY,
                    telegram_id INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    stars INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    meta_json TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
                );

                CREATE INDEX IF NOT EXISTS idx_telegram_payments_user_created
                    ON telegram_payments (telegram_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS user_cosmetics (
                    telegram_id INTEGER NOT NULL,
                    cosmetic_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    meta_json TEXT,
                    acquired_at TEXT NOT NULL,
                    PRIMARY KEY (telegram_id, cosmetic_id),
                    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
                );

                CREATE INDEX IF NOT EXISTS idx_user_cosmetics_user
                    ON user_cosmetics (telegram_id, acquired_at DESC);

                CREATE TABLE IF NOT EXISTS quest_claims (
                    telegram_id INTEGER NOT NULL,
                    quest_id TEXT NOT NULL,
                    period_key TEXT NOT NULL,
                    reward_amount INTEGER NOT NULL,
                    claimed_at TEXT NOT NULL,
                    PRIMARY KEY (telegram_id, quest_id, period_key),
                    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
                );

                CREATE INDEX IF NOT EXISTS idx_quest_claims_user_period
                    ON quest_claims (telegram_id, period_key);

                CREATE TABLE IF NOT EXISTS achievement_claims (
                    telegram_id INTEGER NOT NULL,
                    achievement_id TEXT NOT NULL,
                    reward_amount INTEGER NOT NULL,
                    claimed_at TEXT NOT NULL,
                    PRIMARY KEY (telegram_id, achievement_id),
                    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
                );

                CREATE TABLE IF NOT EXISTS season_reward_claims (
                    telegram_id INTEGER NOT NULL,
                    season_key TEXT NOT NULL,
                    level INTEGER NOT NULL,
                    tier TEXT NOT NULL,
                    reward_amount INTEGER NOT NULL,
                    claimed_at TEXT NOT NULL,
                    PRIMARY KEY (telegram_id, season_key, level, tier),
                    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
                );
                """
            )
            payment_columns = self._columns(conn, "telegram_payments")
            self._add_column(conn, payment_columns, "telegram_payments", "refunded_at", "TEXT")
            self._add_column(conn, payment_columns, "telegram_payments", "refund_meta_json", "TEXT")

    @staticmethod
    def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
        return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}

    @staticmethod
    def _add_column(conn: sqlite3.Connection, existing: set[str], table: str, column: str, definition: str) -> None:
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            existing.add(column)

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    def parse_time(value: str | None) -> datetime | None:
        if not value:
            return None
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row else None

    @staticmethod
    def _read_attr(source: Any, *names: str, default: Any = "") -> Any:
        for name in names:
            if isinstance(source, dict) and name in source:
                return source[name]
            if hasattr(source, name):
                return getattr(source, name)
        return default

    def ensure_user(self, tg_user: Any, is_admin: bool = False) -> dict[str, Any]:
        telegram_id = int(self._read_attr(tg_user, "id"))
        now = self.now()
        username = self._read_attr(tg_user, "username", default=None)
        first_name = self._read_attr(tg_user, "first_name", default=None)
        last_name = self._read_attr(tg_user, "last_name", default=None)
        admin_flag = 1 if is_admin else 0

        with self.user_lock(telegram_id), self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO users (
                    telegram_id, username, first_name, last_name, balance,
                    is_admin, created_at, updated_at, last_seen_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    username = excluded.username,
                    first_name = excluded.first_name,
                    last_name = excluded.last_name,
                    is_admin = excluded.is_admin,
                    updated_at = excluded.updated_at,
                    last_seen_at = excluded.last_seen_at
                """,
                (
                    telegram_id,
                    username,
                    first_name,
                    last_name,
                    DEFAULT_START_BALANCE,
                    admin_flag,
                    now,
                    now,
                    now,
                ),
            )
            return self._row(
                conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
            )

    def get_user(self, telegram_id: int) -> dict[str, Any] | None:
        with self.connection() as conn:
            return self._row(conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone())

    def users_by_telegram_ids(self, telegram_ids: Iterable[int]) -> dict[int, dict[str, Any]]:
        ids = list(dict.fromkeys(int(telegram_id) for telegram_id in telegram_ids))
        if not ids:
            return {}

        placeholders = ", ".join("?" for _ in ids)
        with self.connection() as conn:
            rows = conn.execute(
                f"SELECT * FROM users WHERE telegram_id IN ({placeholders})",
                ids,
            ).fetchall()
            return {int(row["telegram_id"]): dict(row) for row in rows}

    def list_users(
        self,
        limit: int = 50,
        offset: int = 0,
        query: str | None = None,
    ) -> list[dict[str, Any]]:
        where, params = self._user_search_clause(query)
        with self.connection() as conn:
            rows = conn.execute(
                f"SELECT * FROM users {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ).fetchall()
            return [dict(row) for row in rows]

    def count_users(self, query: str | None = None) -> int:
        where, params = self._user_search_clause(query)
        with self.connection() as conn:
            return int(conn.execute(f"SELECT COUNT(*) FROM users {where}", params).fetchone()[0])

    @staticmethod
    def _user_search_clause(query: str | None) -> tuple[str, tuple[Any, ...]]:
        if not query or not query.strip():
            return "", ()
        term = query.strip().lstrip("@")
        like = f"%{term}%"
        clause = (
            "WHERE CAST(telegram_id AS TEXT) LIKE ? "
            "OR username LIKE ? COLLATE NOCASE "
            "OR first_name LIKE ? COLLATE NOCASE "
            "OR last_name LIKE ? COLLATE NOCASE"
        )
        return clause, (like, like, like, like)

    def leaderboard(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT telegram_id, username, first_name, last_name, balance, referral_count
                FROM users
                WHERE COALESCE(is_banned, 0) = 0
                ORDER BY balance DESC, referral_count DESC, created_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    @staticmethod
    def _week_start(now_dt: datetime) -> datetime:
        return (now_dt - timedelta(days=now_dt.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    def _weekly_top(self, start_iso: str, end_iso: str | None, limit: int) -> list[dict[str, Any]]:
        end_clause = "AND g.created_at < ?" if end_iso else ""
        params: tuple[Any, ...] = (start_iso, end_iso, limit) if end_iso else (start_iso, limit)
        with self.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT g.telegram_id, u.username, u.first_name, u.last_name,
                       COUNT(*) AS games_count,
                       COALESCE(SUM(g.win_amount), 0) AS weekly_won
                FROM games_log g
                JOIN users u ON u.telegram_id = g.telegram_id
                WHERE g.created_at >= ? {end_clause} AND COALESCE(u.is_banned, 0) = 0
                GROUP BY g.telegram_id
                HAVING weekly_won > 0
                ORDER BY weekly_won DESC, games_count DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
            return [dict(row) for row in rows]

    def weekly_leaderboard(self, limit: int = 100) -> list[dict[str, Any]]:
        """Top players of the current ISO week (Mon 00:00 UTC) by total winnings."""
        start = self._week_start(datetime.now(timezone.utc)).isoformat(timespec="seconds")
        return self._weekly_top(start, None, limit)

    def payout_weekly_rewards(self) -> list[dict[str, Any]]:
        """Pay WEEKLY_REWARD_AMOUNTS to last week's top-3 exactly once per week.

        Guarded by runtime_state so restarts and repeated ticker calls are safe.
        Returns the winners paid on this call (empty on every later call).
        """
        now_dt = datetime.now(timezone.utc)
        this_week_start = self._week_start(now_dt)
        prev_week_start = this_week_start - timedelta(days=7)
        iso = prev_week_start.isocalendar()
        prev_week_key = f"{iso.year}-W{iso.week:02d}"
        state = self.get_runtime_state("weekly_rewards_paid") or {}
        if state.get("week") == prev_week_key:
            return []

        top = self._weekly_top(
            prev_week_start.isoformat(timespec="seconds"),
            this_week_start.isoformat(timespec="seconds"),
            len(WEEKLY_REWARD_AMOUNTS),
        )
        winners: list[dict[str, Any]] = []
        for place, row in enumerate(top, start=1):
            amount = WEEKLY_REWARD_AMOUNTS[place - 1]
            try:
                self.adjust_balance(
                    int(row["telegram_id"]),
                    amount,
                    "weekly_reward",
                    meta={"week": prev_week_key, "place": place},
                )
            except BalanceError:
                continue
            winners.append(
                {
                    "telegram_id": int(row["telegram_id"]),
                    "place": place,
                    "amount": amount,
                    "weekly_won": int(row["weekly_won"]),
                }
            )
        self.set_runtime_state(
            "weekly_rewards_paid",
            {"week": prev_week_key, "paid_at": self.now(), "winners": winners},
        )
        return winners

    def quests_ready_notification(self, telegram_id: int) -> int | None:
        """Once per day: number of completed-but-unclaimed quests when >= 3, else None."""
        now_dt = datetime.now(timezone.utc)
        today_start = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        period_key = today_start.date().isoformat()
        user = self.get_user(telegram_id)
        if user is None or user.get("quest_notify_period") == period_key:
            return None
        if not int(user.get("bonus_notify_enabled") or 0):
            return None
        quests = self._quest_rows(telegram_id, today_start, period_key)
        ready = sum(1 for quest in quests if quest["complete"] and not quest["claimed"])
        if ready < 3:
            return None
        with self.transaction() as conn:
            conn.execute(
                "UPDATE users SET quest_notify_period = ? WHERE telegram_id = ? AND COALESCE(quest_notify_period, '') != ?",
                (period_key, telegram_id, period_key),
            )
        return ready

    def admin_stats(self) -> dict[str, Any]:
        with self.connection() as conn:
            users_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            total_balance = conn.execute("SELECT COALESCE(SUM(balance), 0) FROM users").fetchone()[0]
            games_count = conn.execute("SELECT COUNT(*) FROM games_log").fetchone()[0]
            total_bets = conn.execute("SELECT COALESCE(SUM(bet), 0) FROM games_log").fetchone()[0]
            total_wins = conn.execute("SELECT COALESCE(SUM(win_amount), 0) FROM games_log").fetchone()[0]
            banned_users_count = conn.execute("SELECT COUNT(*) FROM users WHERE COALESCE(is_banned, 0) = 1").fetchone()[0]
            legal_users_count = conn.execute("SELECT COUNT(*) FROM users WHERE legal_accepted_at IS NOT NULL").fetchone()[0]
            payments_count = conn.execute("SELECT COUNT(*) FROM telegram_payments").fetchone()[0]
            total_stars = conn.execute(
                "SELECT COALESCE(SUM(stars), 0) FROM telegram_payments WHERE refunded_at IS NULL"
            ).fetchone()[0]
            refunded_payments_count = conn.execute(
                "SELECT COUNT(*) FROM telegram_payments WHERE refunded_at IS NOT NULL"
            ).fetchone()[0]
            refunded_stars = conn.execute(
                "SELECT COALESCE(SUM(stars), 0) FROM telegram_payments WHERE refunded_at IS NOT NULL"
            ).fetchone()[0]
            return {
                "users_count": users_count,
                "total_balance": total_balance,
                "games_count": games_count,
                "total_bets": total_bets,
                "total_wins": total_wins,
                "banned_users_count": banned_users_count,
                "legal_users_count": legal_users_count,
                "payments_count": payments_count,
                "total_stars": total_stars,
                "refunded_payments_count": refunded_payments_count,
                "refunded_stars": refunded_stars,
            }

    def admin_overview(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        day_ago = (now - timedelta(hours=24)).isoformat(timespec="seconds")
        week_ago = (now - timedelta(days=7)).isoformat(timespec="seconds")
        stats = self.admin_stats()
        with self.connection() as conn:
            stats["users_new_24h"] = conn.execute(
                "SELECT COUNT(*) FROM users WHERE created_at >= ?", (day_ago,)
            ).fetchone()[0]
            stats["users_active_24h"] = conn.execute(
                "SELECT COUNT(*) FROM users WHERE last_seen_at >= ?", (day_ago,)
            ).fetchone()[0]
            stats["users_active_7d"] = conn.execute(
                "SELECT COUNT(*) FROM users WHERE last_seen_at >= ?", (week_ago,)
            ).fetchone()[0]
            day_row = conn.execute(
                """
                SELECT COUNT(*) AS games, COALESCE(SUM(bet), 0) AS bets, COALESCE(SUM(win_amount), 0) AS payouts
                FROM games_log WHERE created_at >= ?
                """,
                (day_ago,),
            ).fetchone()
            stats["games_24h"] = int(day_row["games"] or 0)
            stats["bets_24h"] = int(day_row["bets"] or 0)
            stats["payouts_24h"] = int(day_row["payouts"] or 0)
            stats["house_net_24h"] = stats["bets_24h"] - stats["payouts_24h"]
            game_rows = conn.execute(
                """
                SELECT game, COUNT(*) AS count,
                       COALESCE(SUM(bet), 0) AS bets, COALESCE(SUM(win_amount), 0) AS payouts
                FROM games_log
                WHERE created_at >= ?
                GROUP BY game
                ORDER BY count DESC
                """,
                (week_ago,),
            ).fetchall()
        top_count = max((int(row["count"]) for row in game_rows), default=0)
        stats["by_game"] = [
            {
                "game": row["game"],
                "count": int(row["count"]),
                "bets": int(row["bets"]),
                "payouts": int(row["payouts"]),
                "net": int(row["bets"]) - int(row["payouts"]),
                "share": round(int(row["count"]) / top_count * 100) if top_count else 0,
            }
            for row in game_rows
        ]
        return stats

    def admin_set_entitlement(
        self,
        telegram_id: int,
        kind: str,
        days: int | None,
        admin_id: int,
    ) -> dict[str, Any] | None:
        column = {"premium": "premium_until", "season_pass": "season_pass_until"}.get(kind)
        if column is None:
            raise BalanceError("Unknown entitlement kind")
        if days is not None and not (1 <= days <= 3650):
            raise BalanceError("Days must be between 1 and 3650")

        with self.user_lock(telegram_id), self.transaction() as conn:
            user = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
            if user is None:
                return None
            now_dt = datetime.now(timezone.utc)
            now = now_dt.isoformat(timespec="seconds")
            if days is None:
                new_value = None
            else:
                new_value = self._extend_until(user[column], now_dt, timedelta(days=days)).isoformat(timespec="seconds")
            conn.execute(
                f"UPDATE users SET {column} = ?, updated_at = ? WHERE telegram_id = ?",
                (new_value, now, telegram_id),
            )
            conn.execute(
                """
                INSERT INTO balance_events (
                    telegram_id, amount, reason, balance_before, balance_after, meta_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    telegram_id,
                    0,
                    f"admin_{kind}",
                    int(user["balance"]),
                    int(user["balance"]),
                    json.dumps({"admin_id": admin_id, "days": days, "until": new_value}, ensure_ascii=False),
                    now,
                ),
            )
            return self._row(conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone())

    def admin_set_luck_factor(self, telegram_id: int, value: Any, admin_id: int) -> dict[str, Any] | None:
        try:
            luck = float(value)
        except (TypeError, ValueError) as exc:
            raise BalanceError("Bad luck factor") from exc
        luck = max(0.25, min(2.0, round(luck, 2)))

        with self.user_lock(telegram_id), self.transaction() as conn:
            user = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
            if user is None:
                return None
            now = self.now()
            conn.execute(
                "UPDATE users SET luck_factor = ?, updated_at = ? WHERE telegram_id = ?",
                (luck, now, telegram_id),
            )
            conn.execute(
                """
                INSERT INTO balance_events (
                    telegram_id, amount, reason, balance_before, balance_after, meta_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    telegram_id,
                    0,
                    "admin_luck",
                    int(user["balance"]),
                    int(user["balance"]),
                    json.dumps({"admin_id": admin_id, "luck_factor": luck}, ensure_ascii=False),
                    now,
                ),
            )
            return self._row(conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone())

    def user_stats(self, telegram_id: int) -> dict[str, Any]:
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS games_count,
                    COALESCE(SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END), 0) AS wins_count,
                    COALESCE(SUM(CASE WHEN outcome = 'lose' THEN 1 ELSE 0 END), 0) AS losses_count,
                    COALESCE(SUM(CASE WHEN outcome = 'pending' THEN 1 ELSE 0 END), 0) AS pending_count,
                    COALESCE(SUM(bet), 0) AS total_bet,
                    COALESCE(SUM(win_amount), 0) AS total_payout,
                    COALESCE(MAX(win_amount), 0) AS best_payout
                FROM games_log
                WHERE telegram_id = ?
                """,
                (telegram_id,),
            ).fetchone()
            return dict(row)

    def player_history(self, telegram_id: int, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        offset = max(0, int(offset))
        # Both sources are fetched up to offset+limit, merged by time, then sliced —
        # so the offset applies to the combined timeline, not each table separately.
        fetch = offset + limit
        with self.connection() as conn:
            games = conn.execute(
                """
                SELECT id, created_at, game AS kind, outcome, bet, win_amount,
                       multiplier, balance_after, meta_json
                FROM games_log
                WHERE telegram_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (telegram_id, fetch),
            ).fetchall()
            events = conn.execute(
                """
                SELECT id, created_at, reason AS kind, amount, balance_after, meta_json
                FROM balance_events
                WHERE telegram_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (telegram_id, fetch),
            ).fetchall()

        rows: list[dict[str, Any]] = []
        for row in games:
            item = dict(row)
            item["type"] = "game"
            item["meta"] = self._json_dict(item.pop("meta_json", None))
            rows.append(item)
        for row in events:
            item = dict(row)
            item["type"] = "balance"
            item["outcome"] = "credit" if int(item.get("amount") or 0) >= 0 else "debit"
            item["meta"] = self._json_dict(item.pop("meta_json", None))
            rows.append(item)
        rows.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return rows[offset:offset + limit]

    @staticmethod
    def _json_dict(value: str | None) -> dict[str, Any]:
        if not value:
            return {}
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def recent_games(self, limit: int = 50, telegram_id: int | None = None) -> list[dict[str, Any]]:
        where = ""
        params: tuple[Any, ...] = (limit,)
        if telegram_id is not None:
            where = "WHERE games_log.telegram_id = ?"
            params = (telegram_id, limit)

        with self.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT games_log.*, users.username, users.first_name
                FROM games_log
                LEFT JOIN users ON users.telegram_id = games_log.telegram_id
                {where}
                ORDER BY games_log.created_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
            return [dict(row) for row in rows]

    def record_game(
        self,
        telegram_id: int,
        game: str,
        bet: int,
        multiplier: float,
        win_amount: int,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if bet <= 0:
            raise BalanceError("Bet must be greater than zero")
        if win_amount < 0:
            raise BalanceError("Win amount cannot be negative")

        with self.user_lock(telegram_id), self.transaction() as conn:
            user = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
            if user is None:
                raise BalanceError("User is not registered")

            balance_before = int(user["balance"])
            if balance_before < bet:
                raise BalanceError("Not enough balance")

            balance_after = balance_before - bet + win_amount
            now = self.now()
            outcome = "win" if win_amount > bet else "draw" if win_amount == bet else "lose"
            conn.execute(
                """
                UPDATE users
                SET balance = ?, updated_at = ?, last_seen_at = ?
                WHERE telegram_id = ?
                """,
                (balance_after, now, now, telegram_id),
            )
            conn.execute(
                """
                INSERT INTO games_log (
                    telegram_id, game, bet, multiplier, outcome, win_amount,
                    balance_before, balance_after, meta_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    telegram_id,
                    game,
                    bet,
                    multiplier,
                    outcome,
                    win_amount,
                    balance_before,
                    balance_after,
                    json.dumps(meta or {}, ensure_ascii=False),
                    now,
                ),
            )
            return {
                "telegram_id": telegram_id,
                "game": game,
                "bet": bet,
                "multiplier": multiplier,
                "outcome": outcome,
                "win_amount": win_amount,
                "balance_before": balance_before,
                "balance_after": balance_after,
                "meta": meta or {},
            }

    def debit_for_pending_game(self, telegram_id: int, game: str, bet: int, meta: dict[str, Any] | None = None) -> dict[str, Any]:
        if bet <= 0:
            raise BalanceError("Bet must be greater than zero")

        with self.user_lock(telegram_id), self.transaction() as conn:
            user = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
            if user is None:
                raise BalanceError("User is not registered")
            balance_before = int(user["balance"])
            if balance_before < bet:
                raise BalanceError("Not enough balance")

            balance_after = balance_before - bet
            now = self.now()
            conn.execute(
                "UPDATE users SET balance = ?, updated_at = ?, last_seen_at = ? WHERE telegram_id = ?",
                (balance_after, now, now, telegram_id),
            )
            conn.execute(
                """
                INSERT INTO games_log (
                    telegram_id, game, bet, multiplier, outcome, win_amount,
                    balance_before, balance_after, meta_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    telegram_id,
                    game,
                    bet,
                    0,
                    "pending",
                    0,
                    balance_before,
                    balance_after,
                    json.dumps(meta or {}, ensure_ascii=False),
                    now,
                ),
            )
            log_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            return {"log_id": log_id, "balance_before": balance_before, "balance_after": balance_after}

    def finalize_pending_game(
        self,
        telegram_id: int,
        log_id: int,
        multiplier: float,
        win_amount: int,
        outcome: str,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if win_amount < 0:
            raise BalanceError("Win amount cannot be negative")

        with self.user_lock(telegram_id), self.transaction() as conn:
            user = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
            if user is None:
                raise BalanceError("User is not registered")

            log = conn.execute(
                "SELECT * FROM games_log WHERE id = ? AND telegram_id = ? AND outcome = 'pending'",
                (log_id, telegram_id),
            ).fetchone()
            if log is None:
                raise BalanceError("Game session is not pending")

            balance_before = int(user["balance"])
            balance_after = balance_before + win_amount
            now = self.now()
            conn.execute(
                "UPDATE users SET balance = ?, updated_at = ?, last_seen_at = ? WHERE telegram_id = ?",
                (balance_after, now, now, telegram_id),
            )
            merged_meta = {}
            if log["meta_json"]:
                try:
                    merged_meta.update(json.loads(log["meta_json"]))
                except json.JSONDecodeError:
                    pass
            merged_meta.update(meta or {})
            conn.execute(
                """
                UPDATE games_log
                SET multiplier = ?, outcome = ?, win_amount = ?,
                    balance_after = ?, meta_json = ?
                WHERE id = ?
                """,
                (multiplier, outcome, win_amount, balance_after, json.dumps(merged_meta, ensure_ascii=False), log_id),
            )
            return {
                "log_id": log_id,
                "telegram_id": telegram_id,
                "bet": int(log["bet"]),
                "multiplier": multiplier,
                "outcome": outcome,
                "win_amount": win_amount,
                "balance_after": balance_after,
            }

    def all_telegram_ids(self) -> list[int]:
        with self.connection() as conn:
            return [
                int(row[0])
                for row in conn.execute("SELECT telegram_id FROM users WHERE COALESCE(is_banned, 0) = 0").fetchall()
            ]

    def adjust_balance(
        self,
        telegram_id: int,
        amount: int,
        reason: str,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if amount == 0:
            raise BalanceError("Amount cannot be zero")

        with self.user_lock(telegram_id), self.transaction() as conn:
            user = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
            if user is None:
                raise BalanceError("User is not registered")

            balance_before = int(user["balance"])
            balance_after = balance_before + int(amount)
            if balance_after < 0:
                raise BalanceError("Balance cannot become negative")
            now = self.now()
            conn.execute(
                "UPDATE users SET balance = ?, updated_at = ?, last_seen_at = ? WHERE telegram_id = ?",
                (balance_after, now, now, telegram_id),
            )
            conn.execute(
                """
                INSERT INTO balance_events (
                    telegram_id, amount, reason, balance_before, balance_after, meta_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    telegram_id,
                    int(amount),
                    reason,
                    balance_before,
                    balance_after,
                    json.dumps(meta or {}, ensure_ascii=False),
                    now,
                ),
            )
            return {
                "telegram_id": telegram_id,
                "amount": int(amount),
                "reason": reason,
                "balance_before": balance_before,
                "balance_after": balance_after,
            }

    def set_upgrader_preference(self, telegram_id: int, multiplier: float, chance: float) -> dict[str, Any]:
        with self.user_lock(telegram_id), self.transaction() as conn:
            now = self.now()
            conn.execute(
                """
                UPDATE users
                SET upgrader_multiplier = ?, upgrader_chance = ?, updated_at = ?, last_seen_at = ?
                WHERE telegram_id = ?
                """,
                (multiplier, chance, now, now, telegram_id),
            )
            return self._row(conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone())

    def set_bonus_notify_enabled(self, telegram_id: int, enabled: bool) -> dict[str, Any]:
        with self.user_lock(telegram_id), self.transaction() as conn:
            now = self.now()
            conn.execute(
                """
                UPDATE users
                SET bonus_notify_enabled = ?, updated_at = ?, last_seen_at = ?
                WHERE telegram_id = ?
                """,
                (1 if enabled else 0, now, now, telegram_id),
            )
            return self._row(conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone())

    def set_user_ban(
        self,
        telegram_id: int,
        banned: bool,
        reason: str = "",
        admin_id: int | None = None,
    ) -> dict[str, Any] | None:
        with self.user_lock(telegram_id), self.transaction() as conn:
            user = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
            if user is None:
                return None
            now = self.now()
            conn.execute(
                """
                UPDATE users
                SET is_banned = ?, ban_reason = ?, banned_at = ?,
                    updated_at = ?, last_seen_at = ?
                WHERE telegram_id = ?
                """,
                (1 if banned else 0, reason.strip() or None, now if banned else None, now, now, telegram_id),
            )
            conn.execute(
                """
                INSERT INTO balance_events (
                    telegram_id, amount, reason, balance_before, balance_after, meta_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    telegram_id,
                    0,
                    "admin_ban" if banned else "admin_unban",
                    int(user["balance"]),
                    int(user["balance"]),
                    json.dumps({"admin_id": admin_id, "reason": reason}, ensure_ascii=False),
                    now,
                ),
            )
            return self._row(conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone())

    @staticmethod
    def _season_xp(user: dict[str, Any], stats: dict[str, Any]) -> int:
        xp = int(stats.get("games_count") or 0) * 10 + int(stats.get("wins_count") or 0) * 15
        xp += int(user.get("best_daily_streak") or 0) * 25 + int(user.get("referral_count") or 0) * 75
        return xp

    @staticmethod
    def _season_level(season_xp: int) -> int:
        return max(1, min(SEASON_MAX_LEVEL, season_xp // SEASON_LEVEL_XP + 1))

    def retention_status(self, telegram_id: int) -> dict[str, Any]:
        user = self.get_user(telegram_id)
        if user is None:
            raise BalanceError("User is not registered")
        now_dt = datetime.now(timezone.utc)
        today_start = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        period_key = today_start.date().isoformat()
        quests = self._quest_rows(telegram_id, today_start, period_key)
        stats = self.user_stats(telegram_id)
        premium_until = self.parse_time(user.get("premium_until"))
        season_pass_until = self.parse_time(user.get("season_pass_until"))
        season_xp = self._season_xp(user, stats)
        level = self._season_level(season_xp)
        return {
            "streak": {
                "current": int(user.get("daily_streak_count") or 0),
                "best": int(user.get("best_daily_streak") or 0),
            },
            "premium": {
                "active": premium_until is not None and premium_until > now_dt,
                "until": user.get("premium_until"),
            },
            "season": {
                "level": level,
                "xp": season_xp,
                "next_level_xp": level * SEASON_LEVEL_XP,
                "pass_active": season_pass_until is not None and season_pass_until > now_dt,
                "pass_until": user.get("season_pass_until"),
                "max_level": SEASON_MAX_LEVEL,
                "track": self._season_track(telegram_id, level),
            },
            "quests": quests,
            "achievements": self.achievements_status(telegram_id),
            "cosmetics": self.user_cosmetics(telegram_id),
            "active_cosmetic": user.get("active_cosmetic"),
        }

    def _season_track(self, telegram_id: int, level_now: int) -> list[dict[str, Any]]:
        with self.connection() as conn:
            claimed = {
                (int(row["level"]), str(row["tier"]))
                for row in conn.execute(
                    "SELECT level, tier FROM season_reward_claims WHERE telegram_id = ? AND season_key = ?",
                    (telegram_id, SEASON_KEY),
                ).fetchall()
            }
        track = []
        for level in range(2, SEASON_MAX_LEVEL + 1):
            rewards = season_level_rewards(level)
            track.append(
                {
                    "level": level,
                    "unlocked": level_now >= level,
                    "free": {"reward": rewards["free"], "claimed": (level, "free") in claimed},
                    "premium": {"reward": rewards["premium"], "claimed": (level, "premium") in claimed},
                }
            )
        return track

    def claim_season_reward(self, telegram_id: int, level_value: Any, tier_value: Any) -> dict[str, Any]:
        try:
            level = int(level_value)
        except (TypeError, ValueError) as exc:
            raise BalanceError("Bad season level") from exc
        tier = str(tier_value or "").strip().lower()
        if tier not in {"free", "premium"}:
            raise BalanceError("Bad reward tier")
        if level < 2 or level > SEASON_MAX_LEVEL:
            raise BalanceError("Bad season level")

        user = self.get_user(telegram_id)
        if user is None:
            raise BalanceError("User is not registered")
        stats = self.user_stats(telegram_id)
        if self._season_level(self._season_xp(user, stats)) < level:
            raise BalanceError("Season level is not reached")
        if tier == "premium":
            now_dt = datetime.now(timezone.utc)
            pass_until = self.parse_time(user.get("season_pass_until"))
            if pass_until is None or pass_until <= now_dt:
                raise BalanceError("Season Pass is not active")

        reward = int(season_level_rewards(level)[tier])
        with self.user_lock(telegram_id), self.transaction() as conn:
            row = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
            if row is None:
                raise BalanceError("User is not registered")
            now = self.now()
            inserted = conn.execute(
                """
                INSERT OR IGNORE INTO season_reward_claims (
                    telegram_id, season_key, level, tier, reward_amount, claimed_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (telegram_id, SEASON_KEY, level, tier, reward, now),
            ).rowcount
            if inserted == 0:
                raise BalanceError("Season reward is already claimed")

            balance_before = int(row["balance"])
            balance_after = balance_before + reward
            conn.execute(
                "UPDATE users SET balance = ?, updated_at = ?, last_seen_at = ? WHERE telegram_id = ?",
                (balance_after, now, now, telegram_id),
            )
            conn.execute(
                """
                INSERT INTO balance_events (
                    telegram_id, amount, reason, balance_before, balance_after, meta_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    telegram_id,
                    reward,
                    "season_reward",
                    balance_before,
                    balance_after,
                    json.dumps({"season_key": SEASON_KEY, "level": level, "tier": tier}, ensure_ascii=False),
                    now,
                ),
            )
        return {"level": level, "tier": tier, "reward": reward, "balance_after": balance_after}

    def _achievement_progress(self, telegram_id: int) -> dict[str, int]:
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS games_count,
                    COALESCE(SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END), 0) AS wins_count,
                    COALESCE(SUM(bet), 0) AS total_bet,
                    COUNT(DISTINCT game) AS distinct_games,
                    COALESCE(MAX(CASE WHEN outcome = 'win' THEN multiplier ELSE 0 END), 0) AS best_win_multiplier
                FROM games_log
                WHERE telegram_id = ?
                """,
                (telegram_id,),
            ).fetchone()
            user = conn.execute(
                "SELECT best_daily_streak, referral_count FROM users WHERE telegram_id = ?",
                (telegram_id,),
            ).fetchone()
        games = int(row["games_count"] or 0)
        wins = int(row["wins_count"] or 0)
        streak = int(user["best_daily_streak"] or 0) if user else 0
        referrals = int(user["referral_count"] or 0) if user else 0
        return {
            "first_win": wins,
            "games_50": games,
            "games_250": games,
            "games_1000": games,
            "wins_100": wins,
            "big_x10": 1 if float(row["best_win_multiplier"] or 0) >= 10 else 0,
            "streak_7": streak,
            "streak_30": streak,
            "invite_3": referrals,
            "invite_10": referrals,
            "all_games": int(row["distinct_games"] or 0),
            "total_bet_100k": int(row["total_bet"] or 0),
        }

    def achievements_status(self, telegram_id: int) -> list[dict[str, Any]]:
        progress = self._achievement_progress(telegram_id)
        with self.connection() as conn:
            claimed = {
                row["achievement_id"]
                for row in conn.execute(
                    "SELECT achievement_id FROM achievement_claims WHERE telegram_id = ?",
                    (telegram_id,),
                ).fetchall()
            }
        rows = []
        for item in ACHIEVEMENTS:
            raw = int(progress.get(item["id"], 0))
            rows.append(
                {
                    "id": item["id"],
                    "target": int(item["target"]),
                    "reward": int(item["reward"]),
                    "progress": min(raw, int(item["target"])),
                    "complete": raw >= int(item["target"]),
                    "claimed": item["id"] in claimed,
                }
            )
        return rows

    def claim_achievement(self, telegram_id: int, achievement_id: str) -> dict[str, Any]:
        item = next((row for row in ACHIEVEMENTS if row["id"] == achievement_id), None)
        if item is None:
            raise BalanceError("Unknown achievement")
        progress = int(self._achievement_progress(telegram_id).get(achievement_id, 0))
        if progress < int(item["target"]):
            raise BalanceError("Achievement is not complete")

        reward = int(item["reward"])
        with self.user_lock(telegram_id), self.transaction() as conn:
            user = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
            if user is None:
                raise BalanceError("User is not registered")
            now = self.now()
            inserted = conn.execute(
                """
                INSERT OR IGNORE INTO achievement_claims (
                    telegram_id, achievement_id, reward_amount, claimed_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (telegram_id, achievement_id, reward, now),
            ).rowcount
            if inserted == 0:
                raise BalanceError("Achievement reward is already claimed")

            balance_before = int(user["balance"])
            balance_after = balance_before + reward
            conn.execute(
                "UPDATE users SET balance = ?, updated_at = ?, last_seen_at = ? WHERE telegram_id = ?",
                (balance_after, now, now, telegram_id),
            )
            conn.execute(
                """
                INSERT INTO balance_events (
                    telegram_id, amount, reason, balance_before, balance_after, meta_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    telegram_id,
                    reward,
                    "achievement",
                    balance_before,
                    balance_after,
                    json.dumps({"achievement_id": achievement_id}, ensure_ascii=False),
                    now,
                ),
            )
        return {"achievement_id": achievement_id, "reward": reward, "balance_after": balance_after}

    def _quest_rows(self, telegram_id: int, today_start: datetime, period_key: str) -> list[dict[str, Any]]:
        since = today_start.isoformat(timespec="seconds")
        with self.connection() as conn:
            today = conn.execute(
                """
                SELECT
                    COUNT(*) AS games_today,
                    COUNT(DISTINCT game) AS distinct_games,
                    COALESCE(SUM(CASE WHEN game = 'roulette' THEN 1 ELSE 0 END), 0) AS roulette_today,
                    COALESCE(SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END), 0) AS wins_today,
                    COALESCE(SUM(CASE WHEN outcome = 'win' AND multiplier >= 5 THEN 1 ELSE 0 END), 0) AS big_wins_today,
                    COALESCE(SUM(CASE WHEN game = 'crash' AND outcome IN ('win', 'draw') THEN 1 ELSE 0 END), 0) AS crash_cashouts_today,
                    COALESCE(SUM(bet), 0) AS bet_volume_today
                FROM games_log
                WHERE telegram_id = ? AND created_at >= ?
                """,
                (telegram_id, since),
            ).fetchone()
            daily_bonus_today = conn.execute(
                """
                SELECT COUNT(*) FROM balance_events
                WHERE telegram_id = ? AND reason = 'daily_bonus' AND created_at >= ?
                """,
                (telegram_id, since),
            ).fetchone()[0]
            user = conn.execute("SELECT referral_count FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
            claims = {
                row["quest_id"]: row
                for row in conn.execute(
                    "SELECT * FROM quest_claims WHERE telegram_id = ? AND period_key IN (?, 'all')",
                    (telegram_id, period_key),
                ).fetchall()
            }

        rows = [
            self._quest_row("daily_bonus", period_key, daily_bonus_today, 1, claims),
            self._quest_row("play_5", period_key, int(today["games_today"] or 0), 5, claims),
            self._quest_row("win_3", period_key, int(today["wins_today"] or 0), 3, claims),
            self._quest_row("try_3_games", period_key, int(today["distinct_games"] or 0), 3, claims),
            self._quest_row("big_win", period_key, int(today["big_wins_today"] or 0), 1, claims),
            self._quest_row("crash_cashout", period_key, int(today["crash_cashouts_today"] or 0), 1, claims),
            self._quest_row("roulette_room", period_key, int(today["roulette_today"] or 0), 1, claims),
            self._quest_row("volume_1000", period_key, int(today["bet_volume_today"] or 0), 1000, claims),
            self._quest_row("invite_1", "all", int(user["referral_count"] if user else 0), 1, claims),
        ]
        return rows

    @staticmethod
    def _quest_row(
        quest_id: str,
        period_key: str,
        progress: int,
        target: int,
        claims: dict[str, sqlite3.Row],
    ) -> dict[str, Any]:
        progress = max(0, int(progress))
        claimed = quest_id in claims
        return {
            "id": quest_id,
            "period_key": period_key,
            "progress": min(progress, target),
            "target": target,
            "reward": QUEST_REWARDS[quest_id],
            "complete": progress >= target,
            "claimed": claimed,
        }

    def claim_quest_reward(self, telegram_id: int, quest_id: str) -> dict[str, Any]:
        now_dt = datetime.now(timezone.utc)
        today_start = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        period_key = today_start.date().isoformat()
        quest = next((row for row in self._quest_rows(telegram_id, today_start, period_key) if row["id"] == quest_id), None)
        if quest is None:
            raise BalanceError("Unknown quest")
        if not quest["complete"]:
            raise BalanceError("Quest is not complete")
        if quest["claimed"]:
            raise BalanceError("Quest reward is already claimed")

        reward = int(quest["reward"])
        with self.user_lock(telegram_id), self.transaction() as conn:
            user = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
            if user is None:
                raise BalanceError("User is not registered")
            now = self.now()
            inserted = conn.execute(
                """
                INSERT OR IGNORE INTO quest_claims (
                    telegram_id, quest_id, period_key, reward_amount, claimed_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (telegram_id, quest_id, quest["period_key"], reward, now),
            ).rowcount
            if inserted == 0:
                raise BalanceError("Quest reward is already claimed")

            balance_before = int(user["balance"])
            balance_after = balance_before + reward
            conn.execute(
                "UPDATE users SET balance = ?, updated_at = ?, last_seen_at = ? WHERE telegram_id = ?",
                (balance_after, now, now, telegram_id),
            )
            conn.execute(
                """
                INSERT INTO balance_events (
                    telegram_id, amount, reason, balance_before, balance_after, meta_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    telegram_id,
                    reward,
                    "quest_reward",
                    balance_before,
                    balance_after,
                    json.dumps({"quest_id": quest_id, "period_key": quest["period_key"]}, ensure_ascii=False),
                    now,
                ),
            )
        return {"quest_id": quest_id, "reward": reward, "balance_after": balance_after}

    def user_cosmetics(self, telegram_id: int) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT cosmetic_id, source, meta_json, acquired_at
                FROM user_cosmetics
                WHERE telegram_id = ?
                ORDER BY acquired_at DESC
                """,
                (telegram_id,),
            ).fetchall()
            return [dict(row) | {"meta": self._json_dict(row["meta_json"])} for row in rows]

    def set_active_cosmetic(self, telegram_id: int, cosmetic_id: str | None) -> dict[str, Any]:
        cosmetic_id = (cosmetic_id or "").strip() or None
        with self.user_lock(telegram_id), self.transaction() as conn:
            if cosmetic_id is not None:
                owned = conn.execute(
                    "SELECT 1 FROM user_cosmetics WHERE telegram_id = ? AND cosmetic_id = ?",
                    (telegram_id, cosmetic_id),
                ).fetchone()
                if owned is None:
                    raise BalanceError("Cosmetic is not owned")
            now = self.now()
            conn.execute(
                """
                UPDATE users
                SET active_cosmetic = ?, updated_at = ?, last_seen_at = ?
                WHERE telegram_id = ?
                """,
                (cosmetic_id, now, now, telegram_id),
            )
            return self._row(conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone())

    def apply_shop_purchase(
        self,
        telegram_id: int,
        kind: str,
        stars: int,
        payment_charge_id: str,
        payload: str,
    ) -> dict[str, Any]:
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat(timespec="seconds")
        with self.user_lock(telegram_id), self.transaction() as conn:
            user = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
            if user is None:
                raise BalanceError("User is not registered")
            payment_meta = {
                "stars": stars,
                "kind": kind,
                "previous_active_cosmetic": user["active_cosmetic"],
                "previous_premium_until": user["premium_until"],
                "previous_season_pass_until": user["season_pass_until"],
            }
            inserted = conn.execute(
                """
                INSERT OR IGNORE INTO telegram_payments (
                    telegram_payment_charge_id, telegram_id, kind, stars,
                    payload, meta_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payment_charge_id,
                    telegram_id,
                    kind,
                    int(stars),
                    payload,
                    json.dumps(payment_meta, ensure_ascii=False),
                    now,
                ),
            ).rowcount
            if inserted == 0:
                return {"applied": False, "duplicate": True, "kind": kind}

            if kind.startswith("cosmetic_"):
                cosmetic_id = kind.removeprefix("cosmetic_")
                payment_meta["cosmetic_id"] = cosmetic_id
                conn.execute(
                    """
                    INSERT OR IGNORE INTO user_cosmetics (
                        telegram_id, cosmetic_id, source, meta_json, acquired_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        telegram_id,
                        cosmetic_id,
                        "stars_shop",
                        json.dumps({"stars": stars, "kind": kind}, ensure_ascii=False),
                        now,
                    ),
                )
                conn.execute(
                    """
                    UPDATE users
                    SET active_cosmetic = COALESCE(active_cosmetic, ?),
                        updated_at = ?, last_seen_at = ?
                    WHERE telegram_id = ?
                    """,
                    (cosmetic_id, now, now, telegram_id),
                )
                applied = {"applied": True, "kind": kind, "cosmetic_id": cosmetic_id}
            elif kind == "premium_30d":
                until = self._extend_until(user["premium_until"], now_dt, timedelta(days=30))
                payment_meta["applied_premium_until"] = until.isoformat(timespec="seconds")
                conn.execute(
                    "UPDATE users SET premium_until = ?, updated_at = ?, last_seen_at = ? WHERE telegram_id = ?",
                    (until.isoformat(timespec="seconds"), now, now, telegram_id),
                )
                applied = {"applied": True, "kind": kind, "premium_until": until.isoformat(timespec="seconds")}
            elif kind == "season_pass":
                until = self._extend_until(user["season_pass_until"], now_dt, timedelta(days=60))
                payment_meta["applied_season_pass_until"] = until.isoformat(timespec="seconds")
                conn.execute(
                    "UPDATE users SET season_pass_until = ?, updated_at = ?, last_seen_at = ? WHERE telegram_id = ?",
                    (until.isoformat(timespec="seconds"), now, now, telegram_id),
                )
                applied = {"applied": True, "kind": kind, "season_pass_until": until.isoformat(timespec="seconds")}
            else:
                raise BalanceError("Unsupported shop item")

            conn.execute(
                "UPDATE telegram_payments SET meta_json = ? WHERE telegram_payment_charge_id = ?",
                (json.dumps(payment_meta, ensure_ascii=False), payment_charge_id),
            )

            conn.execute(
                """
                INSERT INTO balance_events (
                    telegram_id, amount, reason, balance_before, balance_after, meta_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    telegram_id,
                    0,
                    "stars_shop",
                    int(user["balance"]),
                    int(user["balance"]),
                    json.dumps({"kind": kind, "stars": stars, "telegram_payment_charge_id": payment_charge_id}, ensure_ascii=False),
                    now,
                ),
            )
            return applied

    def _extend_until(self, current_value: str | None, now_dt: datetime, delta: timedelta) -> datetime:
        current = self.parse_time(current_value)
        base = current if current and current > now_dt else now_dt
        return base + delta

    def mark_legal_accepted(self, telegram_id: int) -> dict[str, Any]:
        with self.user_lock(telegram_id), self.transaction() as conn:
            now = self.now()
            conn.execute(
                """
                UPDATE users
                SET legal_accepted_at = COALESCE(legal_accepted_at, ?),
                    updated_at = ?, last_seen_at = ?
                WHERE telegram_id = ?
                """,
                (now, now, now, telegram_id),
            )
            user = self._row(conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone())
        self.finalize_referral_reward(telegram_id)
        return self.get_user(telegram_id) or user

    def apply_referral(self, telegram_id: int, referrer_id: int) -> dict[str, Any]:
        if telegram_id == referrer_id:
            return {"applied": False, "reason": "self"}

        first, second = sorted((telegram_id, referrer_id))
        with self.user_lock(first), self.user_lock(second), self.transaction() as conn:
            user = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
            referrer = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (referrer_id,)).fetchone()
            if user is None or referrer is None:
                return {"applied": False, "reason": "missing_user"}
            if user["referred_by"]:
                return {"applied": False, "reason": "already_referred"}
            if referrer["referred_by"] and int(referrer["referred_by"]) == telegram_id:
                return {"applied": False, "reason": "mutual_referral"}
            if int(referrer["is_banned"] or 0):
                return {"applied": False, "reason": "referrer_banned"}

            now = self.now()
            conn.execute(
                "UPDATE users SET referred_by = ?, referral_rewarded_at = NULL, updated_at = ? WHERE telegram_id = ?",
                (referrer_id, now, telegram_id),
            )
        rewarded = self.finalize_referral_reward(telegram_id)
        return {
            "applied": True,
            "referrer_id": referrer_id,
            "telegram_id": telegram_id,
            "reward_pending": not rewarded.get("rewarded", False),
            **rewarded,
        }

    def finalize_referral_reward(self, telegram_id: int) -> dict[str, Any]:
        user = self.get_user(telegram_id)
        if not user or not user.get("referred_by") or user.get("referral_rewarded_at"):
            return {"rewarded": False, "reason": "not_eligible"}
        if not user.get("legal_accepted_at"):
            return {"rewarded": False, "reason": "legal_not_accepted"}
        if int(user.get("is_banned") or 0):
            return {"rewarded": False, "reason": "banned"}

        referrer_id = int(user["referred_by"])
        first, second = sorted((telegram_id, referrer_id))
        with self.user_lock(first), self.user_lock(second), self.transaction() as conn:
            user_row = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
            referrer = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (referrer_id,)).fetchone()
            if user_row is None or referrer is None:
                return {"rewarded": False, "reason": "missing_user"}
            if user_row["referral_rewarded_at"]:
                return {"rewarded": False, "reason": "already_rewarded"}
            if not user_row["legal_accepted_at"] or int(user_row["is_banned"] or 0):
                return {"rewarded": False, "reason": "not_eligible"}
            if int(referrer["is_banned"] or 0):
                return {"rewarded": False, "reason": "referrer_banned"}

            now = self.now()
            ref_balance_before = int(referrer["balance"])
            ref_balance_after = ref_balance_before + REFERRAL_REWARD_AMOUNT
            conn.execute(
                """
                UPDATE users
                SET balance = ?, referral_count = referral_count + 1,
                    updated_at = ?, last_seen_at = ?
                WHERE telegram_id = ?
                """,
                (ref_balance_after, now, now, referrer_id),
            )
            conn.execute(
                """
                UPDATE users
                SET referral_rewarded_at = ?, updated_at = ?
                WHERE telegram_id = ?
                """,
                (now, now, telegram_id),
            )
            conn.execute(
                """
                INSERT INTO balance_events (
                    telegram_id, amount, reason, balance_before, balance_after, meta_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    referrer_id,
                    REFERRAL_REWARD_AMOUNT,
                    "referral",
                    ref_balance_before,
                    ref_balance_after,
                    json.dumps({"referred_user_id": telegram_id}, ensure_ascii=False),
                    now,
                ),
            )
            return {
                "rewarded": True,
                "referrer_id": referrer_id,
                "telegram_id": telegram_id,
                "reward": REFERRAL_REWARD_AMOUNT,
                "referrer_balance_after": ref_balance_after,
            }

    @staticmethod
    def _projected_streak(last_value: datetime | None, current_streak: int, now_dt: datetime) -> int:
        """Streak the next claim will reach, mirroring claim_daily_bonus rules."""
        if last_value is None:
            return 1
        if now_dt <= last_value + timedelta(hours=48):
            return current_streak + 1
        return 1

    @classmethod
    def _bonus_snapshot(
        cls,
        last_value: str | None,
        now_dt: datetime,
        current_streak: int = 0,
    ) -> dict[str, Any]:
        last = cls.parse_time(last_value)
        next_at = None if last is None else last + timedelta(hours=24)
        available = last is None or now_dt >= next_at
        seconds_left = 0 if available else max(0, int((next_at - now_dt).total_seconds()))
        projected_streak = cls._projected_streak(last, current_streak, now_dt)
        return {
            "available": available,
            "amount": daily_bonus_amount(projected_streak),
            "next_streak": projected_streak,
            "last_daily_bonus_at": last_value,
            "next_at": next_at.isoformat(timespec="seconds") if next_at else None,
            "seconds_left": seconds_left,
        }

    def daily_bonus_status(self, telegram_id: int) -> dict[str, Any]:
        user = self.get_user(telegram_id)
        if user is None:
            raise BalanceError("User is not registered")
        snapshot = self._bonus_snapshot(
            user.get("last_daily_bonus_at"),
            datetime.now(timezone.utc),
            int(user.get("daily_streak_count") or 0),
        )
        snapshot["streak_count"] = int(user.get("daily_streak_count") or 0)
        snapshot["best_streak"] = int(user.get("best_daily_streak") or 0)
        return snapshot

    def claim_daily_bonus(self, telegram_id: int) -> dict[str, Any]:
        with self.user_lock(telegram_id), self.transaction() as conn:
            user = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
            if user is None:
                raise BalanceError("User is not registered")

            now_dt = datetime.now(timezone.utc)
            last = self.parse_time(user["last_daily_bonus_at"])
            next_at = None if last is None else last + timedelta(hours=24)
            if last is not None and now_dt < next_at:
                current_streak = int(user["daily_streak_count"] or 0)
                return {
                    "claimed": False,
                    "available": False,
                    "amount": daily_bonus_amount(self._projected_streak(last, current_streak, now_dt)),
                    "next_at": next_at.isoformat(timespec="seconds"),
                    "seconds_left": max(0, int((next_at - now_dt).total_seconds())),
                    "balance_after": int(user["balance"]),
                    "streak_count": current_streak,
                    "best_streak": int(user["best_daily_streak"] or 0),
                }

            previous_streak = int(user["daily_streak_count"] or 0)
            if last is None:
                streak_count = 1
            elif now_dt <= last + timedelta(hours=48):
                streak_count = previous_streak + 1
            else:
                streak_count = 1
            best_streak = max(int(user["best_daily_streak"] or 0), streak_count)
            award = daily_bonus_amount(streak_count)
            balance_before = int(user["balance"])
            balance_after = balance_before + award
            now = now_dt.isoformat(timespec="seconds")
            conn.execute(
                """
                UPDATE users
                SET balance = ?, last_daily_bonus_at = ?, daily_reminder_sent_at = ?,
                    daily_streak_count = ?, best_daily_streak = ?,
                    updated_at = ?, last_seen_at = ?
                WHERE telegram_id = ?
                """,
                (balance_after, now, now, streak_count, best_streak, now, now, telegram_id),
            )
            conn.execute(
                """
                INSERT INTO balance_events (
                    telegram_id, amount, reason, balance_before, balance_after, meta_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    telegram_id,
                    award,
                    "daily_bonus",
                    balance_before,
                    balance_after,
                    json.dumps({"streak": streak_count}, ensure_ascii=False),
                    now,
                ),
            )
            return {
                "claimed": True,
                "available": False,
                "amount": award,
                "balance_after": balance_after,
                "next_at": (now_dt + timedelta(hours=24)).isoformat(timespec="seconds"),
                "seconds_left": 86400,
                "streak_count": streak_count,
                "best_streak": best_streak,
            }

    def renew_daily_bonus(
        self,
        telegram_id: int,
        stars: int,
        payment_charge_id: str,
        payload: str,
    ) -> dict[str, Any]:
        with self.user_lock(telegram_id), self.transaction() as conn:
            user = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
            if user is None:
                raise BalanceError("User is not registered")

            now = self.now()
            payment_meta = {
                "stars": stars,
                "kind": "daily_bonus_renew",
                "previous_last_daily_bonus_at": user["last_daily_bonus_at"],
                "previous_daily_reminder_sent_at": user["daily_reminder_sent_at"],
            }
            inserted = conn.execute(
                """
                INSERT OR IGNORE INTO telegram_payments (
                    telegram_payment_charge_id, telegram_id, kind, stars,
                    payload, meta_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payment_charge_id,
                    telegram_id,
                    "daily_bonus_renew",
                    stars,
                    payload,
                    json.dumps(payment_meta, ensure_ascii=False),
                    now,
                ),
            ).rowcount
            if inserted == 0:
                return {
                    "applied": False,
                    "duplicate": True,
                    "bonus": self._bonus_snapshot(
                        user["last_daily_bonus_at"],
                        datetime.now(timezone.utc),
                        int(user["daily_streak_count"] or 0),
                    ),
                }

            balance = int(user["balance"])
            conn.execute(
                """
                UPDATE users
                SET last_daily_bonus_at = NULL, daily_reminder_sent_at = NULL,
                    updated_at = ?, last_seen_at = ?
                WHERE telegram_id = ?
                """,
                (now, now, telegram_id),
            )
            conn.execute(
                """
                INSERT INTO balance_events (
                    telegram_id, amount, reason, balance_before, balance_after, meta_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    telegram_id,
                    0,
                    "daily_bonus_renew",
                    balance,
                    balance,
                    json.dumps({"stars": stars, "telegram_payment_charge_id": payment_charge_id}, ensure_ascii=False),
                    now,
                ),
            )
            return {
                "applied": True,
                "duplicate": False,
                "bonus": {
                    "available": True,
                    "amount": DAILY_BONUS_AMOUNT,
                    "last_daily_bonus_at": None,
                    "next_at": None,
                    "seconds_left": 0,
                },
            }

    def recent_payments(self, limit: int = 100, telegram_id: int | None = None) -> list[dict[str, Any]]:
        where = ""
        params: tuple[Any, ...] = (limit,)
        if telegram_id is not None:
            where = "WHERE telegram_payments.telegram_id = ?"
            params = (telegram_id, limit)

        with self.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT telegram_payments.*, users.username, users.first_name
                FROM telegram_payments
                LEFT JOIN users ON users.telegram_id = telegram_payments.telegram_id
                {where}
                ORDER BY telegram_payments.created_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
            return [dict(row) for row in rows]

    def get_payment(self, telegram_payment_charge_id: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            return self._row(
                conn.execute(
                    """
                    SELECT telegram_payments.*, users.username, users.first_name
                    FROM telegram_payments
                    LEFT JOIN users ON users.telegram_id = telegram_payments.telegram_id
                    WHERE telegram_payment_charge_id = ?
                    """,
                    (telegram_payment_charge_id,),
                ).fetchone()
            )

    def mark_payment_refunded(
        self,
        telegram_payment_charge_id: str,
        admin_id: int,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        payment_for_lock = self.get_payment(telegram_payment_charge_id)
        if payment_for_lock is None:
            return None

        telegram_id = int(payment_for_lock["telegram_id"])
        with self.user_lock(telegram_id), self.transaction() as conn:
            payment = conn.execute(
                "SELECT * FROM telegram_payments WHERE telegram_payment_charge_id = ?",
                (telegram_payment_charge_id,),
            ).fetchone()
            if payment is None:
                return None
            if payment["refunded_at"]:
                return self._row(payment)

            now = self.now()
            reversal = self._reverse_payment_effect_locked(conn, payment, now)
            refund_meta = {"admin_id": admin_id, "reversal": reversal, **(meta or {})}
            conn.execute(
                """
                UPDATE telegram_payments
                SET refunded_at = COALESCE(refunded_at, ?),
                    refund_meta_json = COALESCE(refund_meta_json, ?)
                WHERE telegram_payment_charge_id = ?
                """,
                (now, json.dumps(refund_meta, ensure_ascii=False), telegram_payment_charge_id),
            )
            user = conn.execute("SELECT balance FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
            if user is not None:
                balance = int(user["balance"])
                conn.execute(
                    """
                    INSERT INTO balance_events (
                        telegram_id, amount, reason, balance_before, balance_after, meta_json, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        telegram_id,
                        0,
                        "stars_refund",
                        balance,
                        balance,
                        json.dumps(
                            {
                                "telegram_payment_charge_id": telegram_payment_charge_id,
                                "kind": payment["kind"],
                                "stars": payment["stars"],
                                "reversal": reversal,
                            },
                            ensure_ascii=False,
                        ),
                        now,
                    ),
                )
        return self.get_payment(telegram_payment_charge_id)

    def _reverse_payment_effect_locked(self, conn: sqlite3.Connection, payment: sqlite3.Row, now: str) -> dict[str, Any]:
        telegram_id = int(payment["telegram_id"])
        kind = str(payment["kind"])
        payment_id = str(payment["telegram_payment_charge_id"])
        payment_meta = self._json_dict(payment["meta_json"])
        user = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
        if user is None:
            return {"applied": False, "reason": "user_missing"}

        if kind == "daily_bonus_renew":
            if user["last_daily_bonus_at"] is not None:
                return {"applied": False, "reason": "daily_bonus_already_claimed_after_purchase"}
            conn.execute(
                """
                UPDATE users
                SET last_daily_bonus_at = ?, daily_reminder_sent_at = ?,
                    updated_at = ?, last_seen_at = ?
                WHERE telegram_id = ?
                """,
                (
                    payment_meta.get("previous_last_daily_bonus_at"),
                    payment_meta.get("previous_daily_reminder_sent_at"),
                    now,
                    now,
                    telegram_id,
                ),
            )
            return {"applied": True, "kind": kind}

        if kind.startswith("cosmetic_"):
            cosmetic_id = str(payment_meta.get("cosmetic_id") or kind.removeprefix("cosmetic_"))
            remaining = conn.execute(
                """
                SELECT COUNT(*)
                FROM telegram_payments
                WHERE telegram_id = ? AND kind = ?
                  AND telegram_payment_charge_id != ?
                  AND refunded_at IS NULL
                """,
                (telegram_id, kind, payment_id),
            ).fetchone()[0]
            if int(remaining) > 0:
                return {"applied": False, "reason": "same_cosmetic_still_owned", "cosmetic_id": cosmetic_id}
            conn.execute(
                "DELETE FROM user_cosmetics WHERE telegram_id = ? AND cosmetic_id = ?",
                (telegram_id, cosmetic_id),
            )
            previous_active = payment_meta.get("previous_active_cosmetic")
            if previous_active:
                owned_previous = conn.execute(
                    "SELECT 1 FROM user_cosmetics WHERE telegram_id = ? AND cosmetic_id = ?",
                    (telegram_id, previous_active),
                ).fetchone()
                if owned_previous is None:
                    previous_active = None
            if user["active_cosmetic"] == cosmetic_id:
                conn.execute(
                    "UPDATE users SET active_cosmetic = ?, updated_at = ?, last_seen_at = ? WHERE telegram_id = ?",
                    (previous_active, now, now, telegram_id),
                )
            return {"applied": True, "kind": kind, "cosmetic_id": cosmetic_id}

        if kind == "premium_30d":
            return self._reverse_time_extension_locked(
                conn=conn,
                telegram_id=telegram_id,
                column="premium_until",
                current_value=user["premium_until"],
                previous_value=payment_meta.get("previous_premium_until"),
                applied_value=payment_meta.get("applied_premium_until"),
                delta=timedelta(days=30),
                now=now,
            )

        if kind == "season_pass":
            return self._reverse_time_extension_locked(
                conn=conn,
                telegram_id=telegram_id,
                column="season_pass_until",
                current_value=user["season_pass_until"],
                previous_value=payment_meta.get("previous_season_pass_until"),
                applied_value=payment_meta.get("applied_season_pass_until"),
                delta=timedelta(days=60),
                now=now,
            )

        return {"applied": False, "reason": "unsupported_kind", "kind": kind}

    def _reverse_time_extension_locked(
        self,
        conn: sqlite3.Connection,
        telegram_id: int,
        column: str,
        current_value: str | None,
        previous_value: str | None,
        applied_value: str | None,
        delta: timedelta,
        now: str,
    ) -> dict[str, Any]:
        current = self.parse_time(current_value)
        if current is None:
            return {"applied": False, "reason": "not_active", "column": column}

        if applied_value and current_value == applied_value:
            new_value = previous_value
        else:
            reduced = current - delta
            now_dt = datetime.now(timezone.utc)
            previous = self.parse_time(previous_value)
            if previous and previous > reduced:
                reduced = previous
            new_value = None if reduced <= now_dt else reduced.isoformat(timespec="seconds")

        conn.execute(
            f"UPDATE users SET {column} = ?, updated_at = ?, last_seen_at = ? WHERE telegram_id = ?",
            (new_value, now, now, telegram_id),
        )
        return {"applied": True, "column": column, "value_after": new_value}

    def get_runtime_state(self, key: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute("SELECT value_json FROM runtime_state WHERE key = ?", (key,)).fetchone()
            if row is None:
                return None
            try:
                return json.loads(row["value_json"])
            except json.JSONDecodeError:
                return None

    def set_runtime_state(self, key: str, value: dict[str, Any]) -> None:
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO runtime_state (key, value_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at = excluded.updated_at
                """,
                (key, json.dumps(value, ensure_ascii=False), self.now()),
            )

    def users_due_daily_reminder(self, limit: int = 200) -> list[int]:
        now_iso = self.now()
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT telegram_id
                FROM users
                WHERE bonus_notify_enabled = 1
                  AND COALESCE(is_banned, 0) = 0
                  AND COALESCE(last_daily_bonus_at, created_at) IS NOT NULL
                  AND datetime(COALESCE(last_daily_bonus_at, created_at), '+24 hours') <= datetime(?)
                  AND (
                    daily_reminder_sent_at IS NULL
                    OR datetime(daily_reminder_sent_at)
                        < datetime(COALESCE(last_daily_bonus_at, created_at), '+24 hours')
                  )
                ORDER BY datetime(COALESCE(last_daily_bonus_at, created_at)) ASC
                LIMIT ?
                """,
                (now_iso, limit),
            ).fetchall()
            return [int(row["telegram_id"]) for row in rows]

    def mark_daily_reminder_sent(self, telegram_id: int) -> None:
        with self.user_lock(telegram_id), self.transaction() as conn:
            conn.execute(
                "UPDATE users SET daily_reminder_sent_at = ? WHERE telegram_id = ?",
                (self.now(), telegram_id),
            )
