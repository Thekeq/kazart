from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone

from db import BalanceError, DataBase
from services.shop import parse_shop_payload, shop_payload


def iso_ago(**kwargs: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(**kwargs)).isoformat(timespec="seconds")


def tg_user(telegram_id: int, username: str) -> dict[str, object]:
    return {
        "id": telegram_id,
        "username": username,
        "first_name": username.title(),
        "last_name": "",
    }


class DataBaseCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = DataBase(":memory:")

    def tearDown(self) -> None:
        self.db.close()

    def test_memory_database_survives_multiple_connections(self) -> None:
        self.db.ensure_user(tg_user(101, "alice"))
        self.db.set_runtime_state("smoke", {"ok": True})

        self.assertEqual(self.db.get_user(101)["username"], "alice")
        self.assertEqual(self.db.get_runtime_state("smoke"), {"ok": True})

    def test_users_by_telegram_ids_deduplicates_and_keeps_missing_out(self) -> None:
        self.db.ensure_user(tg_user(201, "bob"))
        self.db.ensure_user(tg_user(202, "carol"))

        users = self.db.users_by_telegram_ids([202, 201, 202, 999])

        self.assertEqual(set(users), {201, 202})
        self.assertEqual(users[201]["username"], "bob")
        self.assertEqual(users[202]["username"], "carol")

    def test_quest_claim_is_idempotent_after_daily_bonus(self) -> None:
        self.db.ensure_user(tg_user(301, "dana"))
        self.db.claim_daily_bonus(301)

        claim = self.db.claim_quest_reward(301, "daily_bonus")

        self.assertEqual(claim["reward"], 150)
        self.assertEqual(self.db.get_user(301)["balance"], 2150)
        with self.assertRaises(BalanceError):
            self.db.claim_quest_reward(301, "daily_bonus")
        self.assertEqual(self.db.get_user(301)["balance"], 2150)

    def test_cosmetic_purchase_duplicate_and_refund_reversal(self) -> None:
        self.db.ensure_user(tg_user(401, "erin"))
        payload = shop_payload("cosmetic_neon_theme", 15)

        applied = self.db.apply_shop_purchase(401, "cosmetic_neon_theme", 15, "charge-cos-1", payload)
        duplicate = self.db.apply_shop_purchase(401, "cosmetic_neon_theme", 15, "charge-cos-1", payload)

        self.assertTrue(applied["applied"])
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(self.db.get_user(401)["active_cosmetic"], "neon_theme")
        self.assertEqual(self.db.user_cosmetics(401)[0]["cosmetic_id"], "neon_theme")

        payment_meta = json.loads(self.db.get_payment("charge-cos-1")["meta_json"])
        self.assertEqual(payment_meta["cosmetic_id"], "neon_theme")

        refunded = self.db.mark_payment_refunded("charge-cos-1", admin_id=1, meta={"reason": "test"})
        refund_meta = json.loads(refunded["refund_meta_json"])

        self.assertIsNotNone(refunded["refunded_at"])
        self.assertTrue(refund_meta["reversal"]["applied"])
        self.assertIsNone(self.db.get_user(401)["active_cosmetic"])
        self.assertEqual(self.db.user_cosmetics(401), [])

    def test_premium_purchase_refund_restores_previous_until(self) -> None:
        self.db.ensure_user(tg_user(501, "frank"))
        payload = shop_payload("premium_30d", 99)

        self.db.apply_shop_purchase(501, "premium_30d", 99, "charge-premium-1", payload)
        self.assertIsNotNone(self.db.get_user(501)["premium_until"])

        refunded = self.db.mark_payment_refunded("charge-premium-1", admin_id=1)
        refund_meta = json.loads(refunded["refund_meta_json"])

        self.assertTrue(refund_meta["reversal"]["applied"])
        self.assertIsNone(self.db.get_user(501)["premium_until"])


class TimeAndReminderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = DataBase(":memory:")

    def tearDown(self) -> None:
        self.db.close()

    def _set_user_field(self, telegram_id: int, column: str, value: str | None) -> None:
        assert column in {"created_at", "last_daily_bonus_at", "daily_reminder_sent_at"}
        with self.db.transaction() as conn:
            conn.execute(f"UPDATE users SET {column} = ? WHERE telegram_id = ?", (value, telegram_id))

    def test_parse_time_assumes_utc_for_naive_values(self) -> None:
        parsed = DataBase.parse_time("2026-01-01T00:00:00")
        self.assertIsNotNone(parsed.tzinfo)
        aware = DataBase.parse_time("2026-01-01T00:00:00+00:00")
        self.assertEqual(parsed, aware)

    def test_users_due_daily_reminder_filters_in_sql(self) -> None:
        self.db.ensure_user(tg_user(601, "gina"))
        # Fresh user: bonus window not elapsed yet.
        self.assertEqual(self.db.users_due_daily_reminder(), [])

        self._set_user_field(601, "created_at", iso_ago(hours=25))
        self.assertEqual(self.db.users_due_daily_reminder(), [601])

        self.db.mark_daily_reminder_sent(601)
        self.assertEqual(self.db.users_due_daily_reminder(), [])

        # Claim moves the window forward: not due again immediately.
        self.db.claim_daily_bonus(601)
        self.assertEqual(self.db.users_due_daily_reminder(), [])

        # Bonus became available an hour ago, reminder was sent before that: due.
        self._set_user_field(601, "last_daily_bonus_at", iso_ago(hours=25))
        self._set_user_field(601, "daily_reminder_sent_at", iso_ago(hours=2))
        self.assertEqual(self.db.users_due_daily_reminder(), [601])

        # Reminder already sent after availability: not due.
        self._set_user_field(601, "daily_reminder_sent_at", iso_ago(minutes=30))
        self.assertEqual(self.db.users_due_daily_reminder(), [])

        # Banned and notify-off users are excluded.
        self._set_user_field(601, "daily_reminder_sent_at", iso_ago(hours=2))
        self.db.set_bonus_notify_enabled(601, False)
        self.assertEqual(self.db.users_due_daily_reminder(), [])
        self.db.set_bonus_notify_enabled(601, True)
        self.db.set_user_ban(601, True, reason="test")
        self.assertEqual(self.db.users_due_daily_reminder(), [])

    def test_renew_duplicate_reports_actual_bonus_state(self) -> None:
        self.db.ensure_user(tg_user(801, "hank"))
        first = self.db.renew_daily_bonus(801, stars=25, payment_charge_id="charge-renew-1", payload="daily_bonus_renew:25")
        self.assertTrue(first["applied"])
        self.assertTrue(first["bonus"]["available"])

        self.db.claim_daily_bonus(801)
        duplicate = self.db.renew_daily_bonus(801, stars=25, payment_charge_id="charge-renew-1", payload="daily_bonus_renew:25")

        self.assertTrue(duplicate["duplicate"])
        self.assertFalse(duplicate["bonus"]["available"])
        self.assertGreater(duplicate["bonus"]["seconds_left"], 0)


class ReferralTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = DataBase(":memory:")

    def tearDown(self) -> None:
        self.db.close()

    def test_mutual_referral_is_blocked(self) -> None:
        self.db.ensure_user(tg_user(701, "ivan"))
        self.db.ensure_user(tg_user(702, "olha"))

        applied = self.db.apply_referral(701, 702)
        self.assertTrue(applied["applied"])

        mutual = self.db.apply_referral(702, 701)
        self.assertFalse(mutual["applied"])
        self.assertEqual(mutual["reason"], "mutual_referral")

    def test_self_referral_is_blocked(self) -> None:
        self.db.ensure_user(tg_user(703, "petro"))
        result = self.db.apply_referral(703, 703)
        self.assertFalse(result["applied"])

    def test_referral_reward_after_legal_acceptance(self) -> None:
        self.db.ensure_user(tg_user(711, "referrer"))
        self.db.ensure_user(tg_user(712, "invited"))
        self.db.apply_referral(712, 711)
        balance_before = self.db.get_user(711)["balance"]

        self.db.mark_legal_accepted(712)

        referrer = self.db.get_user(711)
        self.assertEqual(referrer["balance"], balance_before + 1000)
        self.assertEqual(referrer["referral_count"], 1)
        # Second acceptance must not double-reward.
        self.db.mark_legal_accepted(712)
        self.assertEqual(self.db.get_user(711)["balance"], balance_before + 1000)


class AdminStatsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = DataBase(":memory:")

    def tearDown(self) -> None:
        self.db.close()

    def test_total_stars_excludes_refunded(self) -> None:
        self.db.ensure_user(tg_user(901, "kate"))
        self.db.apply_shop_purchase(901, "premium_30d", 99, "charge-a", shop_payload("premium_30d", 99))
        self.db.apply_shop_purchase(901, "cosmetic_neon_theme", 15, "charge-b", shop_payload("cosmetic_neon_theme", 15))
        self.db.mark_payment_refunded("charge-b", admin_id=1)

        stats = self.db.admin_stats()

        self.assertEqual(stats["payments_count"], 2)
        self.assertEqual(stats["total_stars"], 99)
        self.assertEqual(stats["refunded_payments_count"], 1)
        self.assertEqual(stats["refunded_stars"], 15)


class RetentionProgressTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = DataBase(":memory:")
        self.db.ensure_user(tg_user(1001, "lena"))

    def tearDown(self) -> None:
        self.db.close()

    def test_new_quests_present_and_track_progress(self) -> None:
        self.db.record_game(1001, "dice", bet=100, multiplier=6.0, win_amount=600)
        pending = self.db.debit_for_pending_game(1001, "crash", bet=50)
        self.db.finalize_pending_game(1001, pending["log_id"], multiplier=2.0, win_amount=100, outcome="win")

        quests = {q["id"]: q for q in self.db.retention_status(1001)["quests"]}

        self.assertEqual(quests["win_3"]["progress"], 2)
        self.assertTrue(quests["big_win"]["complete"])
        self.assertTrue(quests["crash_cashout"]["complete"])
        self.assertEqual(quests["volume_1000"]["progress"], 150)
        self.assertFalse(quests["volume_1000"]["complete"])

    def test_achievement_claim_flow(self) -> None:
        self.db.record_game(1001, "upgrader", bet=10, multiplier=12.0, win_amount=120)

        achievements = {a["id"]: a for a in self.db.achievements_status(1001)}
        self.assertTrue(achievements["first_win"]["complete"])
        self.assertTrue(achievements["big_x10"]["complete"])
        self.assertFalse(achievements["games_50"]["complete"])

        balance_before = self.db.get_user(1001)["balance"]
        claim = self.db.claim_achievement(1001, "first_win")
        self.assertEqual(claim["reward"], 200)
        self.assertEqual(self.db.get_user(1001)["balance"], balance_before + 200)

        with self.assertRaises(BalanceError):
            self.db.claim_achievement(1001, "first_win")
        with self.assertRaises(BalanceError):
            self.db.claim_achievement(1001, "games_50")
        with self.assertRaises(BalanceError):
            self.db.claim_achievement(1001, "no_such_achievement")

    def test_season_track_and_claims(self) -> None:
        # 60 games -> 600+ xp -> level 3+
        for _ in range(60):
            self.db.record_game(1001, "dice", bet=1, multiplier=0.5, win_amount=0)
        status = self.db.retention_status(1001)
        level = status["season"]["level"]
        self.assertGreaterEqual(level, 3)
        self.assertEqual(len(status["season"]["track"]), 49)

        balance_before = self.db.get_user(1001)["balance"]
        claim = self.db.claim_season_reward(1001, 2, "free")
        self.assertEqual(claim["reward"], 200)
        self.assertEqual(self.db.get_user(1001)["balance"], balance_before + 200)

        with self.assertRaises(BalanceError):
            self.db.claim_season_reward(1001, 2, "free")  # duplicate
        with self.assertRaises(BalanceError):
            self.db.claim_season_reward(1001, 49, "free")  # level not reached
        with self.assertRaises(BalanceError):
            self.db.claim_season_reward(1001, 2, "premium")  # no pass

        # Premium unlocks with an active Season Pass
        self.db.apply_shop_purchase(1001, "season_pass", 149, "charge-pass", shop_payload("season_pass", 149))
        claim = self.db.claim_season_reward(1001, 2, "premium")
        self.assertEqual(claim["reward"], 400)

        track = {row["level"]: row for row in self.db.retention_status(1001)["season"]["track"]}
        self.assertTrue(track[2]["free"]["claimed"])
        self.assertTrue(track[2]["premium"]["claimed"])
        self.assertFalse(track[3]["free"]["claimed"])


class AdminToolsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = DataBase(":memory:")
        self.db.ensure_user(tg_user(1101, "mira"))

    def tearDown(self) -> None:
        self.db.close()

    def test_user_search_and_pagination(self) -> None:
        self.db.ensure_user(tg_user(2201, "alexboss"))
        self.db.ensure_user(tg_user(2202, "alexfan"))
        self.db.ensure_user(tg_user(2203, "zoe"))

        self.assertEqual(self.db.count_users(), 4)
        self.assertEqual(self.db.count_users("alex"), 2)
        self.assertEqual(self.db.count_users("@ALEXBOSS"), 1)  # case-insensitive, @ stripped
        self.assertEqual(self.db.count_users("2203"), 1)  # by telegram id
        ids = {u["telegram_id"] for u in self.db.list_users(query="alex")}
        self.assertEqual(ids, {2201, 2202})
        page1 = self.db.list_users(limit=2, offset=0)
        page2 = self.db.list_users(limit=2, offset=2)
        self.assertEqual(len(page1), 2)
        self.assertEqual(len(page2), 2)
        self.assertFalse({u["telegram_id"] for u in page1} & {u["telegram_id"] for u in page2})

    def test_admin_entitlement_grant_and_revoke(self) -> None:
        user = self.db.admin_set_entitlement(1101, "premium", 30, admin_id=1)
        self.assertIsNotNone(user["premium_until"])
        first_until = user["premium_until"]

        # Granting again extends from the current expiry.
        user = self.db.admin_set_entitlement(1101, "premium", 30, admin_id=1)
        self.assertGreater(user["premium_until"], first_until)

        user = self.db.admin_set_entitlement(1101, "premium", None, admin_id=1)
        self.assertIsNone(user["premium_until"])

        user = self.db.admin_set_entitlement(1101, "season_pass", 60, admin_id=1)
        self.assertIsNotNone(user["season_pass_until"])

        with self.assertRaises(BalanceError):
            self.db.admin_set_entitlement(1101, "unknown", 30, admin_id=1)
        with self.assertRaises(BalanceError):
            self.db.admin_set_entitlement(1101, "premium", 0, admin_id=1)
        self.assertIsNone(self.db.admin_set_entitlement(999999, "premium", 30, admin_id=1))

    def test_admin_luck_factor_clamped_and_logged(self) -> None:
        user = self.db.admin_set_luck_factor(1101, 5.0, admin_id=1)
        self.assertEqual(user["luck_factor"], 2.0)
        user = self.db.admin_set_luck_factor(1101, 0.01, admin_id=1)
        self.assertEqual(user["luck_factor"], 0.25)
        user = self.db.admin_set_luck_factor(1101, "1.3", admin_id=1)
        self.assertEqual(user["luck_factor"], 1.3)
        with self.assertRaises(BalanceError):
            self.db.admin_set_luck_factor(1101, "not-a-number", admin_id=1)
        history = self.db.player_history(1101, limit=10)
        self.assertTrue(any(item["kind"] == "admin_luck" for item in history))

    def test_admin_overview_metrics(self) -> None:
        self.db.record_game(1101, "dice", bet=100, multiplier=2.0, win_amount=200)
        self.db.record_game(1101, "plinko", bet=50, multiplier=0.5, win_amount=25)

        stats = self.db.admin_overview()

        self.assertEqual(stats["users_new_24h"], 1)
        self.assertEqual(stats["users_active_24h"], 1)
        self.assertEqual(stats["games_24h"], 2)
        self.assertEqual(stats["bets_24h"], 150)
        self.assertEqual(stats["payouts_24h"], 225)
        self.assertEqual(stats["house_net_24h"], -75)
        by_game = {row["game"]: row for row in stats["by_game"]}
        self.assertEqual(by_game["dice"]["count"], 1)
        self.assertEqual(by_game["dice"]["net"], -100)
        self.assertEqual(max(row["share"] for row in stats["by_game"]), 100)


class LuckMechanicsTests(unittest.TestCase):
    def test_luck_reroll_deterministic_edges(self) -> None:
        from services.games import _luck_rerolls

        # luck 2.0: a loss is always rerolled, a win never is.
        self.assertTrue(all(_luck_rerolls(False, 2.0) for _ in range(50)))
        self.assertFalse(any(_luck_rerolls(True, 2.0) for _ in range(50)))
        # luck 1.0: nothing is ever rerolled.
        self.assertFalse(any(_luck_rerolls(False, 1.0) for _ in range(50)))
        self.assertFalse(any(_luck_rerolls(True, 1.0) for _ in range(50)))
        # luck far below 1: wins are rerolled, losses stay.
        self.assertFalse(any(_luck_rerolls(False, 0.25) for _ in range(50)))


class ShopPayloadTests(unittest.TestCase):
    def test_parse_shop_payload_rejects_bad_stars(self) -> None:
        with self.assertRaises(ValueError):
            parse_shop_payload("premium_30d:not-an-int")

    def test_shop_payload_roundtrip(self) -> None:
        payload = shop_payload("season_pass", 149)
        self.assertEqual(parse_shop_payload(payload), ("season_pass", 149))


class StreakBonusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = DataBase(":memory:")
        self.db.ensure_user(tg_user(1301, "nick"))

    def tearDown(self) -> None:
        self.db.close()

    def test_bonus_scales_with_streak(self) -> None:
        from db import daily_bonus_amount

        self.assertEqual(daily_bonus_amount(1), 1000)
        self.assertEqual(daily_bonus_amount(2), 1150)
        self.assertEqual(daily_bonus_amount(7), 1900)
        self.assertEqual(daily_bonus_amount(30), 1900)  # capped at day 7

    def test_first_claim_awards_base(self) -> None:
        result = self.db.claim_daily_bonus(1301)
        self.assertTrue(result["claimed"])
        self.assertEqual(result["amount"], 1000)
        self.assertEqual(result["streak_count"], 1)
        self.assertEqual(self.db.get_user(1301)["balance"], 2000)

    def test_status_projects_next_amount(self) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE users SET daily_streak_count = 3, last_daily_bonus_at = ? WHERE telegram_id = ?",
                (iso_ago(hours=25), 1301),
            )
        status = self.db.daily_bonus_status(1301)
        self.assertTrue(status["available"])
        self.assertEqual(status["next_streak"], 4)
        self.assertEqual(status["amount"], 1450)  # 1000 + 3*150


class WeeklyLeaderboardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = DataBase(":memory:")
        self.db.ensure_user(tg_user(1401, "alpha"))
        self.db.ensure_user(tg_user(1402, "beta"))
        self.db.ensure_user(tg_user(1403, "gamma"))

    def tearDown(self) -> None:
        self.db.close()

    def test_weekly_leaderboard_ranks_by_winnings(self) -> None:
        self.db.record_game(1401, "dice", bet=100, multiplier=2.0, win_amount=200)
        self.db.record_game(1402, "dice", bet=100, multiplier=5.0, win_amount=500)
        self.db.record_game(1403, "dice", bet=100, multiplier=0.0, win_amount=0)

        leaders = self.db.weekly_leaderboard()

        self.assertEqual([row["telegram_id"] for row in leaders], [1402, 1401])
        self.assertEqual(leaders[0]["weekly_won"], 500)
        self.assertEqual(leaders[0]["games_count"], 1)

    def test_weekly_rewards_paid_once_for_previous_week(self) -> None:
        from db import WEEKLY_REWARD_AMOUNTS

        self.db.record_game(1401, "dice", bet=100, multiplier=2.0, win_amount=200)
        self.db.record_game(1402, "dice", bet=100, multiplier=5.0, win_amount=500)
        # Move all games into the previous ISO week.
        with self.db.connection() as conn:
            conn.execute("UPDATE games_log SET created_at = ?", (iso_ago(days=7),))
        before = {uid: self.db.get_user(uid)["balance"] for uid in (1401, 1402)}

        winners = self.db.payout_weekly_rewards()

        self.assertEqual([w["telegram_id"] for w in winners], [1402, 1401])
        self.assertEqual(winners[0]["amount"], WEEKLY_REWARD_AMOUNTS[0])
        self.assertEqual(self.db.get_user(1402)["balance"], before[1402] + WEEKLY_REWARD_AMOUNTS[0])
        self.assertEqual(self.db.get_user(1401)["balance"], before[1401] + WEEKLY_REWARD_AMOUNTS[1])
        # Idempotent: a second call in the same week pays nothing.
        self.assertEqual(self.db.payout_weekly_rewards(), [])

    def test_current_week_games_do_not_trigger_payout(self) -> None:
        self.db.record_game(1401, "dice", bet=100, multiplier=2.0, win_amount=200)
        self.assertEqual(self.db.payout_weekly_rewards(), [])


class QuestNotificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = DataBase(":memory:")
        self.db.ensure_user(tg_user(1501, "questy"))

    def tearDown(self) -> None:
        self.db.close()

    def _complete_many_quests(self) -> None:
        # 5 games, 3 wins, 3 distinct games, 2000 bet volume -> at least
        # play_5, win_3, try_3_games and volume_1000 become ready.
        self.db.record_game(1501, "dice", bet=400, multiplier=2.0, win_amount=800)
        self.db.record_game(1501, "plinko", bet=400, multiplier=2.0, win_amount=800)
        self.db.record_game(1501, "upgrader", bet=400, multiplier=2.0, win_amount=800)
        self.db.record_game(1501, "dice", bet=400, multiplier=0.0, win_amount=0)
        self.db.record_game(1501, "dice", bet=400, multiplier=0.0, win_amount=0)

    def test_notifies_once_per_day_when_three_quests_ready(self) -> None:
        self.assertIsNone(self.db.quests_ready_notification(1501))
        self._complete_many_quests()

        ready = self.db.quests_ready_notification(1501)

        self.assertIsNotNone(ready)
        self.assertGreaterEqual(ready, 3)
        self.assertIsNone(self.db.quests_ready_notification(1501))  # once per day

    def test_respects_notification_opt_out(self) -> None:
        self._complete_many_quests()
        with self.db.transaction() as conn:
            conn.execute("UPDATE users SET bonus_notify_enabled = 0 WHERE telegram_id = ?", (1501,))
        self.assertIsNone(self.db.quests_ready_notification(1501))


class HistoryPaginationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = DataBase(":memory:")
        self.db.ensure_user(tg_user(1601, "pager"))

    def tearDown(self) -> None:
        self.db.close()

    def test_offset_pages_are_disjoint_and_ordered(self) -> None:
        for index in range(6):
            self.db.record_game(1601, "dice", bet=10 + index, multiplier=0.0, win_amount=0)

        first = self.db.player_history(1601, limit=3, offset=0)
        second = self.db.player_history(1601, limit=3, offset=3)

        self.assertEqual(len(first), 3)
        first_keys = {(row["type"], row["id"]) for row in first}
        second_keys = {(row["type"], row["id"]) for row in second}
        self.assertFalse(first_keys & second_keys)
        combined = first + second
        stamps = [row["created_at"] for row in combined]
        self.assertEqual(stamps, sorted(stamps, reverse=True))


class WheelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = DataBase(":memory:")
        self.db.ensure_user(tg_user(1701, "spinner"))

    def tearDown(self) -> None:
        self.db.close()

    def test_prize_tables_are_consistent(self) -> None:
        from db import WHEEL_PRIZES, WHEEL_WEIGHTS

        self.assertEqual(len(WHEEL_PRIZES), len(WHEEL_WEIGHTS))
        self.assertTrue(all(amount > 0 for amount in WHEEL_PRIZES))
        self.assertTrue(all(weight > 0 for weight in WHEEL_WEIGHTS))

    def test_spin_credits_prize_and_blocks_until_cooldown(self) -> None:
        from db import WHEEL_PRIZES

        before = self.db.get_user(1701)["balance"]
        result = self.db.claim_wheel(1701)

        self.assertTrue(result["claimed"])
        self.assertIn(result["amount"], WHEEL_PRIZES)
        self.assertEqual(result["amount"], WHEEL_PRIZES[result["prize_index"]])
        self.assertEqual(result["balance_after"], before + result["amount"])
        self.assertEqual(self.db.get_user(1701)["balance"], before + result["amount"])

        second = self.db.claim_wheel(1701)
        self.assertFalse(second["claimed"])
        self.assertEqual(second["balance_after"], before + result["amount"])
        self.assertFalse(self.db.wheel_status(1701)["available"])

    def test_spin_available_again_after_cooldown(self) -> None:
        self.db.claim_wheel(1701)
        with self.db.transaction() as conn:
            conn.execute("UPDATE users SET last_wheel_at = ?", (iso_ago(hours=13),))

        self.assertTrue(self.db.wheel_status(1701)["available"])
        self.assertTrue(self.db.claim_wheel(1701)["claimed"])


class StreakWarningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = DataBase(":memory:")
        self.db.ensure_user(tg_user(1801, "streaker"))

    def tearDown(self) -> None:
        self.db.close()

    def _set_streak_state(self, streak: int, claimed_hours_ago: float, reminded_hours_ago: float | None) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE users SET daily_streak_count = ?, last_daily_bonus_at = ?, daily_reminder_sent_at = ?",
                (
                    streak,
                    iso_ago(hours=claimed_hours_ago),
                    iso_ago(hours=reminded_hours_ago) if reminded_hours_ago is not None else None,
                ),
            )

    def test_due_inside_burn_window_once(self) -> None:
        self._set_streak_state(streak=5, claimed_hours_ago=45, reminded_hours_ago=20)

        due = self.db.users_due_streak_warning()
        self.assertEqual([row["telegram_id"] for row in due], [1801])
        self.assertEqual(due[0]["daily_streak_count"], 5)

        self.db.mark_daily_reminder_sent(1801)
        self.assertEqual(self.db.users_due_streak_warning(), [])

    def test_not_due_outside_window_or_low_streak(self) -> None:
        self._set_streak_state(streak=5, claimed_hours_ago=30, reminded_hours_ago=None)
        self.assertEqual(self.db.users_due_streak_warning(), [])

        self._set_streak_state(streak=2, claimed_hours_ago=45, reminded_hours_ago=None)
        self.assertEqual(self.db.users_due_streak_warning(), [])

        self._set_streak_state(streak=5, claimed_hours_ago=49, reminded_hours_ago=None)
        self.assertEqual(self.db.users_due_streak_warning(), [])

    def test_opt_out_respected(self) -> None:
        self._set_streak_state(streak=5, claimed_hours_ago=45, reminded_hours_ago=None)
        self.db.set_bonus_notify_enabled(1801, False)
        self.assertEqual(self.db.users_due_streak_warning(), [])


class WeeklyDigestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = DataBase(":memory:")
        for uid, name in ((1901, "winner"), (1902, "player"), (1903, "quiet"), (1904, "optout")):
            self.db.ensure_user(tg_user(uid, name))

    def tearDown(self) -> None:
        self.db.close()

    def test_recipients_are_last_week_players_minus_winners_and_optouts(self) -> None:
        for uid in (1901, 1902, 1904):
            self.db.record_game(uid, "dice", bet=100, multiplier=2.0, win_amount=200)
        with self.db.transaction() as conn:
            conn.execute("UPDATE games_log SET created_at = ?", (iso_ago(days=3),))
        self.db.set_bonus_notify_enabled(1904, False)

        recipients = self.db.weekly_digest_recipients(exclude=[1901])

        self.assertEqual(recipients, [1902])


class RetentionMetricsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = DataBase(":memory:")

    def tearDown(self) -> None:
        self.db.close()

    def test_d1_retention_counts_next_day_players(self) -> None:
        self.db.ensure_user(tg_user(2001, "returned"))
        self.db.ensure_user(tg_user(2002, "churned"))
        self.db.record_game(2001, "dice", bet=10, multiplier=0.0, win_amount=0)
        with self.db.transaction() as conn:
            conn.execute("UPDATE users SET created_at = ?", (iso_ago(days=3),))
            conn.execute("UPDATE games_log SET created_at = ?", (iso_ago(days=2),))

        stats = self.db.admin_overview()

        self.assertEqual(stats["retention_d1"], {"cohort": 2, "returned": 1, "rate": 50})
        self.assertIn("dau", stats)
        self.assertIn("games_per_active_24h", stats)


if __name__ == "__main__":
    unittest.main()
