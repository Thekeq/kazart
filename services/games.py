from __future__ import annotations

import hashlib
import logging
import math
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from config import settings
from db import BalanceError, DataBase


HOUSE_EDGE = 0.04
UPGRADER_MULTIPLIERS = (1.5, 5.0, 10.0)
UPGRADER_MIN_CHANCE = 0.01
UPGRADER_MAX_CHANCE = 75.0

PLINKO_RISK_TABLES: dict[str, dict[str, Any]] = {
    "low": {
        "label": "Низкий",
        "multipliers": (2.0, 1.35, 1.1, 0.95, 0.75, 0.95, 1.1, 1.35, 2.0),
    },
    "medium": {
        "label": "Средний",
        "multipliers": (7.0, 2.4, 1.3, 0.85, 0.35, 0.85, 1.3, 2.4, 7.0),
    },
    "high": {
        "label": "Высокий",
        "multipliers": (12.0, 3.2, 1.4, 0.65, 0.2, 0.65, 1.4, 3.2, 12.0),
    },
    "degen": {
        "label": "Азарт",
        "multipliers": (35.0, 4.0, 1.1, 0.28, 0.05, 0.28, 1.1, 4.0, 35.0),
    },
}

# Binomial-like distribution: middle slots are common, edge slots are rare and pay more.
PLINKO_SLOT_WEIGHTS = (1, 8, 28, 56, 70, 56, 28, 8, 1)
CRASH_COUNTDOWN_SECONDS = 10.0
CRASH_RESULT_HOLD_SECONDS = 10.0
ROULETTE_COUNTDOWN_SECONDS = 10.0
ROULETTE_RESULT_HOLD_SECONDS = 11.0
CRASH_STATE_KEY = "crash_service"
ROULETTE_STATE_KEY = "roulette_service"
ROULETTE_REDS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
ROULETTE_RANGES: dict[str, dict[str, Any]] = {
    "low": {"label": "1-18", "start": 1, "end": 18, "multiplier": 2},
    "high": {"label": "19-36", "start": 19, "end": 36, "multiplier": 2},
    "first12": {"label": "1-12", "start": 1, "end": 12, "multiplier": 3},
    "second12": {"label": "13-24", "start": 13, "end": 24, "multiplier": 3},
    "third12": {"label": "25-36", "start": 25, "end": 36, "multiplier": 3},
}

logger = logging.getLogger(__name__)


class GameError(ValueError):
    pass


def _roll_bps(success_bps: int) -> tuple[bool, int]:
    roll = secrets.randbelow(10_000) + 1
    return roll <= success_bps, roll


def _weighted_index(weights: tuple[int, ...]) -> int:
    point = secrets.randbelow(sum(weights)) + 1
    cursor = 0
    for index, weight in enumerate(weights):
        cursor += weight
        if point <= cursor:
            return index
    return len(weights) - 1


def _normalize_bet(value: Any) -> int:
    try:
        bet = int(value)
    except (TypeError, ValueError) as exc:
        raise GameError("Bad bet") from exc
    if bet < settings.min_bet:
        raise GameError(f"Minimum bet is {settings.min_bet}")
    if bet > settings.max_bet:
        raise GameError(f"Maximum bet is {settings.max_bet}")
    return bet


def _normalize_multiplier(value: Any) -> float:
    try:
        multiplier = float(value)
    except (TypeError, ValueError) as exc:
        raise GameError("Bad multiplier") from exc
    if multiplier <= 0:
        raise GameError("Bad multiplier")
    chance = calculate_upgrader_chance(multiplier)
    if chance < UPGRADER_MIN_CHANCE or chance > UPGRADER_MAX_CHANCE:
        raise GameError("Chance must be between 0.01% and 75%")
    return round(multiplier, 4)


def normalize_upgrader_target(multiplier_value: Any = None, chance_value: Any = None) -> dict[str, float]:
    if chance_value not in (None, ""):
        try:
            chance = float(chance_value)
        except (TypeError, ValueError) as exc:
            raise GameError("Bad chance") from exc
        if chance < UPGRADER_MIN_CHANCE or chance > UPGRADER_MAX_CHANCE:
            raise GameError("Chance must be between 0.01% and 75%")
        multiplier = (1.0 - HOUSE_EDGE) * 100 / chance
        return {"multiplier": round(multiplier, 4), "chance": round(chance, 4)}

    multiplier = _normalize_multiplier(multiplier_value)
    chance = calculate_upgrader_chance(multiplier)
    return {"multiplier": multiplier, "chance": chance}


def _normalize_plinko_risk(value: Any) -> str:
    risk = str(value or "medium").strip().lower()
    if risk not in PLINKO_RISK_TABLES:
        raise GameError("Unsupported Plinko risk")
    return risk


def calculate_upgrader_chance(multiplier: float) -> float:
    return round((1.0 - HOUSE_EDGE) / multiplier * 100, 2)


def _luck_factor(db: DataBase, telegram_id: int) -> float:
    user = db.get_user(telegram_id)
    if not user:
        return 1.0
    try:
        luck = float(user.get("luck_factor") or 1.0)
    except (TypeError, ValueError):
        return 1.0
    return max(0.25, min(2.0, luck))


def _luck_rerolls(won: bool, luck: float) -> bool:
    """Admin-tunable luck: sometimes silently reroll a bad (or good) outcome.

    luck > 1 gives losing rolls a second chance with probability (luck - 1);
    luck < 1 forces winning rolls to be rerolled with probability (1 - luck).
    The reroll result is final either way, so the visible roll always matches
    the visible outcome and nothing leaks to the player.
    """
    if luck > 1.0 and not won:
        return secrets.randbelow(10_000) < int(round(min(1.0, luck - 1.0) * 10_000))
    if luck < 1.0 and won:
        return secrets.randbelow(10_000) < int(round(min(1.0, 1.0 - luck) * 10_000))
    return False


def play_upgrader(
    db: DataBase,
    telegram_id: int,
    bet_value: Any,
    multiplier_value: Any = None,
    chance_value: Any = None,
) -> dict[str, Any]:
    bet = _normalize_bet(bet_value)
    target = normalize_upgrader_target(multiplier_value=multiplier_value, chance_value=chance_value)
    multiplier = target["multiplier"]
    success_bps = max(1, min(9999, int(((1.0 - HOUSE_EDGE) / multiplier) * 10_000)))
    won, roll = _roll_bps(success_bps)
    if _luck_rerolls(won, _luck_factor(db, telegram_id)):
        won, roll = _roll_bps(success_bps)
    payout = int(bet * multiplier) if won else 0
    game = db.record_game(
        telegram_id=telegram_id,
        game="upgrader",
        bet=bet,
        multiplier=multiplier,
        win_amount=payout,
        meta={
            "success_chance": round(success_bps / 100, 2),
            "roll": roll,
            "success_bps": success_bps,
        },
    )
    return {
        **game,
        "success": won,
        "success_chance": round(success_bps / 100, 2),
        "success_bps": success_bps,
        "potential_win": int(bet * multiplier),
        "roll": roll,
        "roll_percent": round(roll / 100, 2),
    }


def play_dice(db: DataBase, telegram_id: int, bet_value: Any, chance_value: Any, direction: str) -> dict[str, Any]:
    bet = _normalize_bet(bet_value)
    try:
        chance = int(chance_value)
    except (TypeError, ValueError) as exc:
        raise GameError("Bad chance") from exc
    if chance < 1 or chance > 90:
        raise GameError("Chance must be between 1 and 90")
    direction = str(direction).lower()
    if direction not in {"under", "over"}:
        raise GameError("Direction must be under or over")

    roll = secrets.randbelow(100) + 1
    won = roll <= chance if direction == "under" else roll > 100 - chance
    if _luck_rerolls(won, _luck_factor(db, telegram_id)):
        roll = secrets.randbelow(100) + 1
        won = roll <= chance if direction == "under" else roll > 100 - chance
    multiplier = round((100 / chance) * (1 - HOUSE_EDGE), 4)
    payout = int(bet * multiplier) if won else 0
    game = db.record_game(
        telegram_id=telegram_id,
        game="dice",
        bet=bet,
        multiplier=multiplier,
        win_amount=payout,
        meta={"chance": chance, "direction": direction, "roll": roll},
    )
    return {
        **game,
        "success": won,
        "chance": chance,
        "direction": direction,
        "roll": roll,
        "target": chance if direction == "under" else 100 - chance,
    }


def play_plinko(db: DataBase, telegram_id: int, bet_value: Any, risk_value: Any = "medium") -> dict[str, Any]:
    bet = _normalize_bet(bet_value)
    risk = _normalize_plinko_risk(risk_value)
    slots = PLINKO_RISK_TABLES[risk]["multipliers"]
    slot_index = _weighted_index(PLINKO_SLOT_WEIGHTS)
    if _luck_rerolls(slots[slot_index] > 1.0, _luck_factor(db, telegram_id)):
        slot_index = _weighted_index(PLINKO_SLOT_WEIGHTS)
    multiplier = slots[slot_index]
    payout = int(bet * multiplier)
    game = db.record_game(
        telegram_id=telegram_id,
        game="plinko",
        bet=bet,
        multiplier=multiplier,
        win_amount=payout,
        meta={"risk": risk, "slot_index": slot_index, "slots": slots},
    )
    return {
        **game,
        "risk": risk,
        "risk_label": PLINKO_RISK_TABLES[risk]["label"],
        "slot_index": slot_index,
        "slots": list(slots),
        "success": payout > bet,
    }


@dataclass
class CrashPlayer:
    telegram_id: int
    bet: int
    log_id: int
    balance_after_bet: int
    cashed_out: bool = False
    cashout_multiplier: float | None = None
    payout: int = 0
    balance_after: int | None = None


@dataclass
class CrashRound:
    round_id: str
    server_seed: str
    server_hash: str
    crash_at: float
    created_at: float
    starts_at: float
    status: str = "countdown"
    started_at: float | None = None
    crashed_at: float | None = None
    players: dict[int, CrashPlayer] = field(default_factory=dict)


class CrashService:
    def __init__(self, db: DataBase):
        self.db = db
        self._guard = threading.RLock()
        self._current_round: CrashRound | None = None
        self._last_round: CrashRound | None = None
        self._round_history: list[dict[str, Any]] = []
        with self._guard:
            self._load_state_locked()

    def place_bet(self, telegram_id: int, bet_value: Any) -> dict[str, Any]:
        bet = _normalize_bet(bet_value)
        with self._guard:
            now = time.time()
            self._refresh_locked(now)
            round_ = self._current_round
            if round_ is None or round_.status == "crashed":
                if round_ is not None:
                    self._remember_round_locked(round_)
                    self._last_round = round_
                round_ = self._create_round_locked(now)
            if round_.status != "countdown":
                raise GameError("Round already started")
            if telegram_id in round_.players:
                raise GameError("You already joined this round")

            pending = self.db.debit_for_pending_game(
                telegram_id=telegram_id,
                game="crash",
                bet=bet,
                meta={"round_id": round_.round_id, "server_hash": round_.server_hash},
            )
            round_.players[telegram_id] = CrashPlayer(
                telegram_id=telegram_id,
                bet=bet,
                log_id=int(pending["log_id"]),
                balance_after_bet=int(pending["balance_after"]),
            )
            self._persist_locked()
            snapshot = self._snapshot_locked(telegram_id, now)
            snapshot["balance_after"] = int(pending["balance_after"])
            return snapshot

    def state(self, telegram_id: int | None = None) -> dict[str, Any]:
        with self._guard:
            now = time.time()
            self._refresh_locked(now)
            return self._snapshot_locked(telegram_id, now)

    def cashout(self, telegram_id: int) -> dict[str, Any]:
        with self._guard:
            now = time.time()
            self._refresh_locked(now)
            round_ = self._current_round
            if round_ is None or round_.status != "running":
                raise GameError("No running Crash round")

            player = round_.players.get(telegram_id)
            if player is None:
                raise GameError("You do not have a bet in this round")
            if player.cashed_out:
                return self._snapshot_locked(telegram_id, now)

            multiplier = self._current_multiplier_locked(round_, now)
            if multiplier >= round_.crash_at:
                self._crash_round_locked(round_, now)
                self._persist_locked()
                return self._snapshot_locked(telegram_id, now)

            multiplier = round(multiplier, 2)
            payout = int(player.bet * multiplier)
            result = self.db.finalize_pending_game(
                telegram_id=telegram_id,
                log_id=player.log_id,
                multiplier=multiplier,
                win_amount=payout,
                outcome="win" if payout > player.bet else "draw",
                meta={
                    "round_id": round_.round_id,
                    "cashout_multiplier": multiplier,
                    "crash_at": round_.crash_at,
                    "server_hash": round_.server_hash,
                },
            )
            player.cashed_out = True
            player.cashout_multiplier = multiplier
            player.payout = payout
            player.balance_after = int(result["balance_after"])
            self._persist_locked()
            snapshot = self._snapshot_locked(telegram_id, now)
            snapshot["cashout"] = {
                "multiplier": multiplier,
                "payout": payout,
                "balance_after": player.balance_after,
            }
            return snapshot

    def _create_round_locked(self, now: float) -> CrashRound:
        seed = secrets.token_urlsafe(32)
        round_ = CrashRound(
            round_id=secrets.token_hex(6),
            server_seed=seed,
            server_hash=hashlib.sha256(seed.encode()).hexdigest(),
            crash_at=self._crash_multiplier_from_seed(seed),
            created_at=now,
            starts_at=now + CRASH_COUNTDOWN_SECONDS,
        )
        self._current_round = round_
        return round_

    def _refresh_locked(self, now: float) -> None:
        round_ = self._current_round
        if round_ is None:
            return
        changed = False
        if round_.status == "countdown" and now >= round_.starts_at:
            round_.status = "running"
            round_.started_at = round_.starts_at
            changed = True
        if round_.status == "running" and self._current_multiplier_locked(round_, now) >= round_.crash_at:
            self._crash_round_locked(round_, now)
            changed = True
        if (
            round_.status == "crashed"
            and round_.crashed_at is not None
            and now - round_.crashed_at >= CRASH_RESULT_HOLD_SECONDS
        ):
            self._remember_round_locked(round_)
            self._last_round = round_
            self._current_round = None
            changed = True
        if changed:
            self._persist_locked()

    def _crash_round_locked(self, round_: CrashRound, now: float) -> None:
        if round_.status != "crashed":
            round_.status = "crashed"
            round_.crashed_at = now
        elif round_.crashed_at is None:
            round_.crashed_at = now

        self._finalize_crashed_round_locked(round_)
        self._remember_round_locked(round_)

    def _finalize_crashed_round_locked(self, round_: CrashRound) -> None:
        for player in round_.players.values():
            if player.cashed_out:
                continue
            if player.balance_after is not None:
                continue
            try:
                result = self.db.finalize_pending_game(
                    telegram_id=player.telegram_id,
                    log_id=player.log_id,
                    multiplier=round_.crash_at,
                    win_amount=0,
                    outcome="lose",
                    meta={
                        "round_id": round_.round_id,
                        "crash_at": round_.crash_at,
                        "server_hash": round_.server_hash,
                        "server_seed": round_.server_seed,
                    },
                )
                player.balance_after = int(result["balance_after"])
            except BalanceError:
                logger.warning(
                    "Crash pending game already finalized or missing",
                    extra={"round_id": round_.round_id, "telegram_id": player.telegram_id, "log_id": player.log_id},
                )

    def _snapshot_locked(self, telegram_id: int | None, now: float) -> dict[str, Any]:
        round_ = self._current_round
        if round_ is None:
            return {
                "status": "idle",
                "multiplier": 1.0,
                "seconds_to_start": None,
                "round": None,
                "player": None,
                "leaderboard": [],
                "round_history": list(self._round_history),
                "last_round": self._public_round(self._last_round, now) if self._last_round else None,
            }

        player = round_.players.get(telegram_id) if telegram_id is not None else None
        return {
            "status": round_.status,
            "multiplier": self._current_multiplier_locked(round_, now),
            "seconds_to_start": max(0, round(round_.starts_at - now, 1)) if round_.status == "countdown" else 0,
            "round": self._public_round(round_, now),
            "player": self._public_player(player) if player else None,
            "leaderboard": self._leaderboard(round_),
            "round_history": list(self._round_history),
            "last_round": self._public_round(self._last_round, now) if self._last_round else None,
        }

    def _remember_round_locked(self, round_: CrashRound) -> None:
        if round_.status != "crashed":
            return
        if self._round_history and self._round_history[0]["round_id"] == round_.round_id:
            return
        entry = {
            "round_id": round_.round_id,
            "crash_at": round_.crash_at,
            "players_count": len(round_.players),
            "total_bet": sum(player.bet for player in round_.players.values()),
        }
        self._round_history = [entry, *[row for row in self._round_history if row["round_id"] != round_.round_id]][:12]

    def _public_round(self, round_: CrashRound | None, now: float) -> dict[str, Any] | None:
        if round_ is None:
            return None
        return {
            "round_id": round_.round_id,
            "status": round_.status,
            "server_hash": round_.server_hash,
            "server_seed": round_.server_seed if round_.status == "crashed" else None,
            "crash_at": round_.crash_at if round_.status == "crashed" else None,
            "multiplier": self._current_multiplier_locked(round_, now),
            "players_count": len(round_.players),
            "total_bet": sum(player.bet for player in round_.players.values()),
        }

    @staticmethod
    def _public_player(player: CrashPlayer | None) -> dict[str, Any] | None:
        if player is None:
            return None
        return {
            "telegram_id": player.telegram_id,
            "bet": player.bet,
            "cashed_out": player.cashed_out,
            "cashout_multiplier": player.cashout_multiplier,
            "payout": player.payout,
            "balance_after": player.balance_after,
        }

    def _leaderboard(self, round_: CrashRound) -> list[dict[str, Any]]:
        leaders = sorted(round_.players.values(), key=lambda player: player.bet, reverse=True)[:10]
        users = self.db.users_by_telegram_ids(player.telegram_id for player in leaders)
        rows = []
        for player in leaders:
            user = users.get(player.telegram_id) or {}
            name = user.get("username") or user.get("first_name") or str(player.telegram_id)
            rows.append(
                {
                    "telegram_id": player.telegram_id,
                    "name": name,
                    "bet": player.bet,
                    "cashed_out": player.cashed_out,
                    "cashout_multiplier": player.cashout_multiplier,
                    "payout": player.payout,
                }
            )
        return rows

    def _load_state_locked(self) -> None:
        state = self.db.get_runtime_state(CRASH_STATE_KEY)
        if not state:
            return
        try:
            self._current_round = self._round_from_dict(state.get("current_round"))
            self._last_round = self._round_from_dict(state.get("last_round"))
            self._round_history = list(state.get("round_history") or [])[:12]
            finalized_after_restore = False
            if self._current_round and self._current_round.status == "crashed":
                self._finalize_crashed_round_locked(self._current_round)
                self._remember_round_locked(self._current_round)
                finalized_after_restore = True
            self._refresh_locked(time.time())
            if finalized_after_restore and self._current_round is not None:
                self._persist_locked()
        except Exception:
            logger.exception("Failed to load Crash runtime state")
            self._current_round = None
            self._last_round = None
            self._round_history = []

    def _persist_locked(self) -> None:
        self.db.set_runtime_state(
            CRASH_STATE_KEY,
            {
                "version": 1,
                "current_round": self._round_to_dict(self._current_round),
                "last_round": self._round_to_dict(self._last_round),
                "round_history": self._round_history[:12],
            },
        )

    @classmethod
    def _round_from_dict(cls, data: dict[str, Any] | None) -> CrashRound | None:
        if not data:
            return None
        players = {}
        for row in data.get("players") or []:
            player = cls._player_from_dict(row)
            players[player.telegram_id] = player
        return CrashRound(
            round_id=str(data["round_id"]),
            server_seed=str(data["server_seed"]),
            server_hash=str(data["server_hash"]),
            crash_at=float(data["crash_at"]),
            created_at=float(data["created_at"]),
            starts_at=float(data["starts_at"]),
            status=str(data.get("status") or "countdown"),
            started_at=cls._optional_float(data.get("started_at")),
            crashed_at=cls._optional_float(data.get("crashed_at")),
            players=players,
        )

    @staticmethod
    def _round_to_dict(round_: CrashRound | None) -> dict[str, Any] | None:
        if round_ is None:
            return None
        return {
            "round_id": round_.round_id,
            "server_seed": round_.server_seed,
            "server_hash": round_.server_hash,
            "crash_at": round_.crash_at,
            "created_at": round_.created_at,
            "starts_at": round_.starts_at,
            "status": round_.status,
            "started_at": round_.started_at,
            "crashed_at": round_.crashed_at,
            "players": [CrashService._player_to_dict(player) for player in round_.players.values()],
        }

    @staticmethod
    def _player_from_dict(data: dict[str, Any]) -> CrashPlayer:
        return CrashPlayer(
            telegram_id=int(data["telegram_id"]),
            bet=int(data["bet"]),
            log_id=int(data["log_id"]),
            balance_after_bet=int(data.get("balance_after_bet") or 0),
            cashed_out=bool(data.get("cashed_out")),
            cashout_multiplier=CrashService._optional_float(data.get("cashout_multiplier")),
            payout=int(data.get("payout") or 0),
            balance_after=CrashService._optional_int(data.get("balance_after")),
        )

    @staticmethod
    def _player_to_dict(player: CrashPlayer) -> dict[str, Any]:
        return {
            "telegram_id": player.telegram_id,
            "bet": player.bet,
            "log_id": player.log_id,
            "balance_after_bet": player.balance_after_bet,
            "cashed_out": player.cashed_out,
            "cashout_multiplier": player.cashout_multiplier,
            "payout": player.payout,
            "balance_after": player.balance_after,
        }

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        return None if value is None else float(value)

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        return None if value is None else int(value)

    @staticmethod
    def _current_multiplier_locked(round_: CrashRound, now: float) -> float:
        if round_.status == "countdown" or round_.started_at is None:
            return 1.0
        if round_.status == "crashed":
            return round_.crash_at
        elapsed = max(0.0, now - round_.started_at)
        return round(1 + elapsed * 0.06 + elapsed * elapsed * 0.006, 2)

    @staticmethod
    def _crash_multiplier_from_seed(seed: str) -> float:
        # Domain-separated hash: the published server_hash is sha256(seed), so the
        # crash point must NOT be derivable from it before the seed is revealed.
        digest = hashlib.sha256(f"{seed}:crash".encode()).hexdigest()
        if int(digest[-2:], 16) < 10:
            return 1.0

        top_52_bits = int(digest[:13], 16)
        max_52_bits = float(0xFFFFFFFFFFFFF)
        random_ratio = top_52_bits / max_52_bits
        raw = (1.0 - HOUSE_EDGE) / max(0.000001, 1.0 - random_ratio)
        return round(max(1.0, min(raw, 100.0)), 2)


@dataclass
class RoulettePlayer:
    telegram_id: int
    bet_type: str
    selection: str
    bet: int
    log_id: int
    balance_after_bet: int
    number: int | None = None
    color: str | None = None
    range_key: str | None = None
    multiplier: int = 36
    payout: int = 0
    balance_after: int | None = None


@dataclass
class RouletteRound:
    round_id: str
    created_at: float
    starts_at: float
    status: str = "countdown"
    winning_number: int | None = None
    resolved_at: float | None = None
    players: dict[int, RoulettePlayer] = field(default_factory=dict)


class RouletteService:
    def __init__(self, db: DataBase):
        self.db = db
        self._guard = threading.RLock()
        self._current_round: RouletteRound | None = None
        self._history: list[dict[str, Any]] = []
        with self._guard:
            self._load_state_locked()

    def place_bet(
        self,
        telegram_id: int,
        bet_value: Any,
        number_value: Any = None,
        bet_type_value: Any = None,
        color_value: Any = None,
        range_value: Any = None,
    ) -> dict[str, Any]:
        bet = _normalize_bet(bet_value)
        selection = self._normalize_bet_selection(
            bet_type_value=bet_type_value,
            number_value=number_value,
            color_value=color_value,
            range_value=range_value,
        )

        with self._guard:
            now = time.time()
            self._refresh_locked(now)
            round_ = self._current_round
            if round_ is None or round_.status == "resolved":
                round_ = self._create_round_locked(now)
            if round_.status != "countdown":
                raise GameError("Round already started")
            if telegram_id in round_.players:
                raise GameError("You already joined this round")

            pending = self.db.debit_for_pending_game(
                telegram_id=telegram_id,
                game="roulette",
                bet=bet,
                meta={"round_id": round_.round_id, **selection},
            )
            round_.players[telegram_id] = RoulettePlayer(
                telegram_id=telegram_id,
                bet_type=selection["bet_type"],
                selection=selection["selection"],
                bet=bet,
                log_id=int(pending["log_id"]),
                balance_after_bet=int(pending["balance_after"]),
                number=selection.get("number"),
                color=selection.get("color"),
                range_key=selection.get("range_key"),
                multiplier=int(selection["multiplier"]),
            )
            self._persist_locked()
            snapshot = self._snapshot_locked(telegram_id, now)
            snapshot["balance_after"] = int(pending["balance_after"])
            return snapshot

    def state(self, telegram_id: int | None = None) -> dict[str, Any]:
        with self._guard:
            now = time.time()
            self._refresh_locked(now)
            return self._snapshot_locked(telegram_id, now)

    @staticmethod
    def _normalize_bet_selection(
        bet_type_value: Any = None,
        number_value: Any = None,
        color_value: Any = None,
        range_value: Any = None,
    ) -> dict[str, Any]:
        bet_type = str(bet_type_value or ("number" if number_value not in (None, "") else "color")).strip().lower()
        if bet_type == "number":
            try:
                number = int(number_value)
            except (TypeError, ValueError) as exc:
                raise GameError("Bad roulette number") from exc
            if number < 0 or number > 36:
                raise GameError("Roulette number must be between 0 and 36")
            return {
                "bet_type": "number",
                "selection": str(number),
                "number": number,
                "multiplier": 36,
            }
        if bet_type == "color":
            color = str(color_value or "").strip().lower()
            if color not in {"red", "black"}:
                raise GameError("Roulette color must be red or black")
            return {
                "bet_type": "color",
                "selection": color,
                "color": color,
                "multiplier": 2,
            }
        if bet_type == "range":
            range_key = str(range_value or "").strip().lower()
            if range_key not in ROULETTE_RANGES:
                raise GameError("Unsupported roulette range")
            row = ROULETTE_RANGES[range_key]
            return {
                "bet_type": "range",
                "selection": row["label"],
                "range_key": range_key,
                "range_start": row["start"],
                "range_end": row["end"],
                "multiplier": row["multiplier"],
            }
        raise GameError("Unsupported roulette bet type")

    def _create_round_locked(self, now: float) -> RouletteRound:
        round_ = RouletteRound(
            round_id=secrets.token_hex(6),
            created_at=now,
            starts_at=now + ROULETTE_COUNTDOWN_SECONDS,
        )
        self._current_round = round_
        return round_

    def _refresh_locked(self, now: float) -> None:
        round_ = self._current_round
        if round_ is None:
            return
        changed = False
        if round_.status == "countdown" and now >= round_.starts_at:
            self._resolve_round_locked(round_, now)
            changed = True
        if (
            round_.status == "resolved"
            and round_.resolved_at is not None
            and now - round_.resolved_at >= ROULETTE_RESULT_HOLD_SECONDS
        ):
            self._current_round = None
            changed = True
        if changed:
            self._persist_locked()

    def _resolve_round_locked(self, round_: RouletteRound, now: float) -> None:
        if round_.status != "resolved":
            number = secrets.randbelow(37)
            round_.status = "resolved"
            round_.winning_number = number
            round_.resolved_at = now
            self._persist_locked()

        self._finalize_resolved_round_locked(round_)
        self._remember_round_locked(round_)

    def _finalize_resolved_round_locked(self, round_: RouletteRound) -> None:
        if round_.winning_number is None:
            return
        for player in round_.players.values():
            if player.balance_after is not None:
                continue
            won = self._player_won(player, round_.winning_number)
            payout = player.bet * player.multiplier if won else 0
            try:
                result = self.db.finalize_pending_game(
                    telegram_id=player.telegram_id,
                    log_id=player.log_id,
                    multiplier=player.multiplier if won else 0,
                    win_amount=payout,
                    outcome="win" if won else "lose",
                    meta={
                        "round_id": round_.round_id,
                        "bet_type": player.bet_type,
                        "selection": player.selection,
                        "number": player.number,
                        "color": player.color,
                        "range_key": player.range_key,
                        "winning_number": round_.winning_number,
                    },
                )
                player.payout = payout
                player.balance_after = int(result["balance_after"])
            except BalanceError:
                logger.warning(
                    "Roulette pending game already finalized or missing",
                    extra={"round_id": round_.round_id, "telegram_id": player.telegram_id, "log_id": player.log_id},
                )

    @staticmethod
    def _player_won(player: RoulettePlayer, winning_number: int) -> bool:
        if player.bet_type == "number":
            return player.number == winning_number
        if player.bet_type == "color":
            if winning_number == 0:
                return False
            return (winning_number in ROULETTE_REDS) if player.color == "red" else (winning_number not in ROULETTE_REDS)
        if player.bet_type == "range":
            row = ROULETTE_RANGES.get(player.range_key or "")
            if not row:
                return False
            return int(row["start"]) <= winning_number <= int(row["end"])
        return False

    def _remember_round_locked(self, round_: RouletteRound) -> None:
        if round_.winning_number is None:
            return
        if self._history and self._history[0]["round_id"] == round_.round_id:
            return
        entry = {
            "round_id": round_.round_id,
            "winning_number": round_.winning_number,
            "players_count": len(round_.players),
            "total_bet": sum(player.bet for player in round_.players.values()),
        }
        self._history = [entry, *[row for row in self._history if row["round_id"] != round_.round_id]][:20]

    def _snapshot_locked(self, telegram_id: int | None, now: float) -> dict[str, Any]:
        round_ = self._current_round
        if round_ is None:
            return {
                "status": "idle",
                "seconds_to_start": None,
                "round": None,
                "player": None,
                "leaderboard": [],
                "history": list(self._history),
            }

        player = round_.players.get(telegram_id) if telegram_id is not None else None
        return {
            "status": round_.status,
            "seconds_to_start": max(0, round(round_.starts_at - now, 1)) if round_.status == "countdown" else 0,
            "round": {
                "round_id": round_.round_id,
                "status": round_.status,
                "winning_number": round_.winning_number,
                "players_count": len(round_.players),
                "total_bet": sum(player.bet for player in round_.players.values()),
            },
            "player": self._public_player(player) if player else None,
            "leaderboard": self._leaderboard(round_),
            "history": list(self._history),
        }

    @staticmethod
    def _public_player(player: RoulettePlayer | None) -> dict[str, Any] | None:
        if player is None:
            return None
        return {
            "telegram_id": player.telegram_id,
            "bet_type": player.bet_type,
            "selection": player.selection,
            "number": player.number,
            "color": player.color,
            "range_key": player.range_key,
            "bet": player.bet,
            "multiplier": player.multiplier,
            "payout": player.payout,
            "balance_after": player.balance_after,
        }

    def _leaderboard(self, round_: RouletteRound) -> list[dict[str, Any]]:
        leaders = sorted(round_.players.values(), key=lambda player: player.bet, reverse=True)[:10]
        users = self.db.users_by_telegram_ids(player.telegram_id for player in leaders)
        rows = []
        for player in leaders:
            user = users.get(player.telegram_id) or {}
            rows.append(
                {
                    "telegram_id": player.telegram_id,
                    "name": user.get("username") or user.get("first_name") or str(player.telegram_id),
                    "bet_type": player.bet_type,
                    "selection": player.selection,
                    "number": player.number,
                    "bet": player.bet,
                    "payout": player.payout,
                }
            )
        return rows

    def _load_state_locked(self) -> None:
        state = self.db.get_runtime_state(ROULETTE_STATE_KEY)
        if not state:
            return
        try:
            self._current_round = self._round_from_dict(state.get("current_round"))
            self._history = list(state.get("history") or [])[:20]
            finalized_after_restore = False
            if self._current_round and self._current_round.status == "resolved":
                self._finalize_resolved_round_locked(self._current_round)
                self._remember_round_locked(self._current_round)
                finalized_after_restore = True
            self._refresh_locked(time.time())
            if finalized_after_restore and self._current_round is not None:
                self._persist_locked()
        except Exception:
            logger.exception("Failed to load Roulette runtime state")
            self._current_round = None
            self._history = []

    def _persist_locked(self) -> None:
        self.db.set_runtime_state(
            ROULETTE_STATE_KEY,
            {
                "version": 1,
                "current_round": self._round_to_dict(self._current_round),
                "history": self._history[:20],
            },
        )

    @classmethod
    def _round_from_dict(cls, data: dict[str, Any] | None) -> RouletteRound | None:
        if not data:
            return None
        players = {}
        for row in data.get("players") or []:
            player = cls._player_from_dict(row)
            players[player.telegram_id] = player
        return RouletteRound(
            round_id=str(data["round_id"]),
            created_at=float(data["created_at"]),
            starts_at=float(data["starts_at"]),
            status=str(data.get("status") or "countdown"),
            winning_number=cls._optional_int(data.get("winning_number")),
            resolved_at=cls._optional_float(data.get("resolved_at")),
            players=players,
        )

    @staticmethod
    def _round_to_dict(round_: RouletteRound | None) -> dict[str, Any] | None:
        if round_ is None:
            return None
        return {
            "round_id": round_.round_id,
            "created_at": round_.created_at,
            "starts_at": round_.starts_at,
            "status": round_.status,
            "winning_number": round_.winning_number,
            "resolved_at": round_.resolved_at,
            "players": [RouletteService._player_to_dict(player) for player in round_.players.values()],
        }

    @staticmethod
    def _player_from_dict(data: dict[str, Any]) -> RoulettePlayer:
        bet_type = str(data.get("bet_type") or "number")
        number = RouletteService._optional_int(data.get("number"))
        selection = str(data.get("selection") or (number if number is not None else ""))
        color = data.get("color")
        range_key = data.get("range_key")
        multiplier = int(data.get("multiplier") or (36 if bet_type == "number" else 2))
        return RoulettePlayer(
            telegram_id=int(data["telegram_id"]),
            bet_type=bet_type,
            selection=selection,
            bet=int(data["bet"]),
            log_id=int(data["log_id"]),
            balance_after_bet=int(data.get("balance_after_bet") or 0),
            number=number,
            color=str(color) if color else None,
            range_key=str(range_key) if range_key else None,
            multiplier=multiplier,
            payout=int(data.get("payout") or 0),
            balance_after=RouletteService._optional_int(data.get("balance_after")),
        )

    @staticmethod
    def _player_to_dict(player: RoulettePlayer) -> dict[str, Any]:
        return {
            "telegram_id": player.telegram_id,
            "bet_type": player.bet_type,
            "selection": player.selection,
            "number": player.number,
            "color": player.color,
            "range_key": player.range_key,
            "multiplier": player.multiplier,
            "bet": player.bet,
            "log_id": player.log_id,
            "balance_after_bet": player.balance_after_bet,
            "payout": player.payout,
            "balance_after": player.balance_after,
        }

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        return None if value is None else float(value)

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        return None if value is None else int(value)
