# -*- coding: utf-8 -*-
"""
tests/test_challenger_wave2_master_audit.py
=============================================================================
CHALLENGER MASTER AUDIT — WAVE 2 VERIFICATION SUITE
Empirical stress-testing and adversarial challenge suite covering:
1. Anti-Flood & Media Albums:
   - Rapid bursts of media group album parts sharing media_group_id.
   - Boundary checks: exceeding MAX_MEDIA_GROUP_ITEMS (15) anti-infinite loop guard
     and interaction with secondary media burst buffer.
   - Interleaved multi-user album streams and expiration windows.
   - Veteran vs newbie tier threshold scaling (newbie, anon, veteran, oldfag, ancient).
   - Dynamic flood multiplier based on account age and posts_count.
   - Mute grace period preventing compounding on in-flight packets.
2. PvP & Robbery:
   - cmd_rob and combat weapons against newbie targets (posts_count < 50) triggering immunity.
   - Full accounting of balance changes in UserTransactions across all rob outcomes:
     (successful theft, reflect shield deflection, pepperspray penalty, tinfoil cut).
   - Target grief protection window (300s) and weapon attacker cooldowns.
   - Cross-board post counting and fallback to Posts table.
3. Economy & Bank Taxes:
   - Dynamic real-time interest evaluation in apply_daily_wealth_tax / _do_tax.
   - Accurate taxation and crystallization of dynamic interest on active bank deposits.
   - Deposit-only user taxation without Users table record.
   - Daily lootbox / shop purchase limits across simulated database reboots.
   - Canonical item key alias unification (trash, gold, whale).
4. AI Persona & Music Roast:
   - Cyberchad self-roasting suppression on automated rate-limit rejection voice notes.
   - VoiceTranscriptions fallback target post resolution.
   - Block 2 multi-user grandparent resolution preventing user identity conflation.
   - Music Roast scale score boundary conditions (0, 10, invalid, oxymorons, suffix deduplication).
=============================================================================
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from unittest import mock
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import aiosqlite

import common.config
import common.database as db_mod
import common.spam_filter as spam_mod
import handlers.message_router as router_mod
import lootbox_engine
import main
import shared_state
from combat_moderation_engine import (
    check_target_grief_protection,
    get_user_posts_count,
    is_newbie,
)
from common.spam_filter import (
    MAX_MEDIA_GROUP_ITEMS,
    MEDIA_GROUP_WINDOW,
    USER_TIERS,
    _seen_media_groups,
    _shadow_mute_applied_ts,
    _user_media_burst_tracker,
    _user_request_timestamps,
    check_flood,
    get_user_tier,
    get_veteran_flood_multiplier,
    is_in_mute_grace_period,
    record_shadow_mute_applied,
    reset_media_burst_tracker,
)


# =============================================================================
# PART 1: ANTI-FLOOD & MEDIA ALBUMS ADVERSARIAL CHALLENGES
# =============================================================================

class TestAntiFloodAndMediaAlbums:
    """Stress-test spam_filter with rapid bursts of media group albums and veteran tiers."""

    @pytest.fixture(autouse=True)
    def clean_spam_state(self):
        _user_request_timestamps.clear()
        _seen_media_groups.clear()
        _shadow_mute_applied_ts.clear()
        _user_media_burst_tracker.clear()
        reset_media_burst_tracker()
        yield
        _user_request_timestamps.clear()
        _seen_media_groups.clear()
        _shadow_mute_applied_ts.clear()
        _user_media_burst_tracker.clear()
        reset_media_burst_tracker()

    def test_rapid_burst_media_group_album_all_pass(self):
        """
        Adversarial test: A burst of 12 album parts sent in rapid succession (1ms intervals)
        sharing the same media_group_id must count as 1 logical message.
        All 11 subsequent parts must pass without triggering burst flood.
        """
        user_id = 10001
        board_id = "b"
        mg_id = "album_burst_999"
        base_ts = time.time()

        for i in range(12):
            ts = base_ts + (i * 0.001)
            is_fl, reason = check_flood(
                user_id=user_id,
                board_id=board_id,
                now_ts=ts,
                posts_count=5,  # Newbie with strict burst limit = 8
                is_media=True,
                media_group_id=mg_id
            )
            assert not is_fl, f"Album element {i+1} flagged as flood: {reason}"

        # Only 1 request recorded in timestamps
        assert len(_user_request_timestamps[user_id]) == 1
        assert _seen_media_groups[user_id][mg_id]["count"] == 12

    def test_media_group_anti_infinite_loop_guard(self):
        """
        Adversarial test: An abusive bot attempts an infinite loop by sending many items
        with the same media_group_id.
        After MAX_MEDIA_GROUP_ITEMS (15), subsequent items fall through to the secondary
        media burst buffer (up to 10 items) and then to standard burst timestamps.
        Sending 35 rapid items MUST trigger Burst flood!
        """
        user_id = 10002
        board_id = "b"
        mg_id = "infinite_exploit_mg"
        base_ts = time.time()

        # Send 15 legitimate parts of album -> all pass
        for i in range(MAX_MEDIA_GROUP_ITEMS):
            ts = base_ts + (i * 0.01)
            is_fl, reason = check_flood(
                user_id=user_id,
                board_id=board_id,
                now_ts=ts,
                posts_count=0,
                is_media=True,
                media_group_id=mg_id
            )
            assert not is_fl, f"Legitimate item {i+1} falsely flagged"

        # Items beyond MAX_MEDIA_GROUP_ITEMS + media burst buffer (10) + burst limit (8)
        # MUST trigger flood!
        flagged = False
        for j in range(MAX_MEDIA_GROUP_ITEMS, MAX_MEDIA_GROUP_ITEMS + 25):
            ts = base_ts + (j * 0.01)
            is_fl, reason = check_flood(
                user_id=user_id,
                board_id=board_id,
                now_ts=ts,
                posts_count=0,
                is_media=True,
                media_group_id=mg_id
            )
            if is_fl:
                flagged = True
                assert "Burst флуд" in reason
                break

        assert flagged, "Infinite media_group_id loop exploit was not stopped by layered flood guards!"

    def test_media_group_expiration_window(self):
        """
        Adversarial test: If a message with the same media_group_id arrives after
        MEDIA_GROUP_WINDOW (30s), the old entry must be expired and a new window started.
        """
        user_id = 10003
        board_id = "b"
        mg_id = "expired_mg_test"
        base_ts = 100000.0

        # Initial album part
        is_fl, _ = check_flood(user_id, board_id, now_ts=base_ts, posts_count=10, is_media=True, media_group_id=mg_id)
        assert not is_fl
        assert _seen_media_groups[user_id][mg_id]["count"] == 1

        # Second part 5s later -> absorbed
        is_fl, _ = check_flood(user_id, board_id, now_ts=base_ts + 5.0, posts_count=10, is_media=True, media_group_id=mg_id)
        assert not is_fl
        assert _seen_media_groups[user_id][mg_id]["count"] == 2

        # Third part 35s later -> expired, resets to new count 1
        is_fl, _ = check_flood(user_id, board_id, now_ts=base_ts + 35.0, posts_count=10, is_media=True, media_group_id=mg_id)
        assert not is_fl
        assert _seen_media_groups[user_id][mg_id]["count"] == 1
        assert _seen_media_groups[user_id][mg_id]["first_ts"] == base_ts + 35.0

    def test_concurrent_interleaved_users_albums(self):
        """
        Adversarial test: Two users send albums concurrently with interleaved packets.
        Ensures user state isolation and zero cross-contamination.
        """
        user_a = 10004
        user_b = 10005
        mg_a = "mg_user_a"
        mg_b = "mg_user_b"
        base_ts = time.time()

        for i in range(10):
            ts_a = base_ts + (i * 0.002)
            ts_b = base_ts + (i * 0.002) + 0.001
            is_fl_a, _ = check_flood(user_a, "b", now_ts=ts_a, posts_count=10, is_media=True, media_group_id=mg_a)
            is_fl_b, _ = check_flood(user_b, "b", now_ts=ts_b, posts_count=10, is_media=True, media_group_id=mg_b)
            assert not is_fl_a
            assert not is_fl_b

        assert len(_user_request_timestamps[user_a]) == 1
        assert len(_user_request_timestamps[user_b]) == 1
        assert _seen_media_groups[user_a][mg_a]["count"] == 10
        assert _seen_media_groups[user_b][mg_b]["count"] == 10

    def test_veteran_vs_newbie_threshold_scaling(self):
        """
        Adversarial test: Verify exact limits and behavioral differentiation across all 5 tiers.
        """
        # Tier boundary configs
        assert get_user_tier(0)["name"] == "Новичок"
        assert get_user_tier(19)["name"] == "Новичок"
        assert get_user_tier(20)["name"] == "Анон"
        assert get_user_tier(99)["name"] == "Анон"
        assert get_user_tier(100)["name"] == "Ветеран"
        assert get_user_tier(499)["name"] == "Ветеран"
        assert get_user_tier(500)["name"] == "Олдфаг"
        assert get_user_tier(1999)["name"] == "Олдфаг"
        assert get_user_tier(2000)["name"] == "Древний Олдфаг"

        # Edge cases: negative, None, large
        assert get_user_tier(-5)["name"] == "Новичок"
        assert get_user_tier(None)["name"] == "Новичок"
        assert get_user_tier(1000000)["name"] == "Древний Олдфаг"

        # Base mute times decrease as tier increases
        assert get_user_tier(0)["flood_base_mute_sec"] == 300.0
        assert get_user_tier(25)["flood_base_mute_sec"] == 240.0
        assert get_user_tier(150)["flood_base_mute_sec"] == 120.0
        assert get_user_tier(600)["flood_base_mute_sec"] == 90.0
        assert get_user_tier(3000)["flood_base_mute_sec"] == 60.0

    def test_burst_discrimination_between_tiers(self):
        """
        Adversarial test:
        - Burst of 9 text messages in 2s:
          * Newbie (burst_limit=8) MUST trigger Burst flood on message 9.
          * Anon (burst_limit=10) MUST PASS all 9 messages.
        - Burst of 11 text messages:
          * Anon (burst_limit=10) MUST trigger Burst flood on message 11.
          * Veteran (burst_limit=12) MUST PASS all 11 messages.
        """
        base_ts = time.time()

        # 1. Newbie with 9 messages
        u_newbie = 20001
        for i in range(8):
            is_fl, _ = check_flood(u_newbie, "b", now_ts=base_ts + (i * 0.1), posts_count=5, is_media=False)
            assert not is_fl
        is_fl_9, reason = check_flood(u_newbie, "b", now_ts=base_ts + 0.9, posts_count=5, is_media=False)
        assert is_fl_9, "Newbie should be flagged on 9th message (burst_limit=8)"
        assert "Burst флуд" in reason

        # 2. Anon with 9 messages -> ALL PASS
        u_anon = 20002
        for i in range(9):
            is_fl, _ = check_flood(u_anon, "b", now_ts=base_ts + (i * 0.1), posts_count=25, is_media=False)
            assert not is_fl, f"Anon flagged on message {i+1}"

        # Anon with 11 messages -> 11th triggers
        for i in range(9, 10):
            is_fl, _ = check_flood(u_anon, "b", now_ts=base_ts + (i * 0.1), posts_count=25, is_media=False)
            assert not is_fl
        is_fl_11, _ = check_flood(u_anon, "b", now_ts=base_ts + 1.1, posts_count=25, is_media=False)
        assert is_fl_11, "Anon should be flagged on 11th message (burst_limit=10)"

        # 3. Veteran with 11 messages -> ALL PASS
        u_vet = 20003
        for i in range(11):
            is_fl, _ = check_flood(u_vet, "b", now_ts=base_ts + (i * 0.1), posts_count=150, is_media=False)
            assert not is_fl, f"Veteran flagged on message {i+1}"

    def test_veteran_flood_multiplier_longevity(self):
        """Dynamic multiplier increases when veteran has >= 30 days account age."""
        mult_young = get_veteran_flood_multiplier(posts_count=150, account_age_days=10.0)
        mult_old = get_veteran_flood_multiplier(posts_count=150, account_age_days=35.0)
        assert mult_young == 1.5
        assert mult_old == 1.6
        assert mult_old > mult_young

    def test_mute_grace_period_boundaries(self):
        """Mute grace period boundary test: 3.99s is inside, 4.01s is outside."""
        uid = 30001
        now = time.time()
        record_shadow_mute_applied(uid, now_ts=now)

        assert is_in_mute_grace_period(uid, now_ts=now) is True
        assert is_in_mute_grace_period(uid, now_ts=now + 3.99) is True
        assert is_in_mute_grace_period(uid, now_ts=now + 4.01) is False
        assert is_in_mute_grace_period(uid, now_ts=now + 10.0) is False


# =============================================================================
# PART 2: PVP & ROBBERY ADVERSARIAL CHALLENGES
# =============================================================================

class TestPvPAndRobbery:
    """Challenge cmd_rob, newbie immunity, UserTransactions ledger, and grief protection."""

    @pytest.fixture(autouse=True)
    def clean_combat_state(self):
        shared_state.reset_combat_state()
        yield
        shared_state.reset_combat_state()

    @pytest.mark.asyncio
    async def test_cmd_rob_newbie_immunity_strictly_enforced(self, isolated_test_db):
        """
        Adversarial test: cmd_rob against targets with 0, 15, 49 posts.
        Must block attack with newbie immunity notice and leave target balance untouched.
        """
        db = isolated_test_db
        board_id = "b"

        for idx, newbie_posts in enumerate([0, 15, 49]):
            attacker_id = 40001 + idx
            target_id = 40100 + newbie_posts

            # Attacker setup
            await db.execute(
                "INSERT OR REPLACE INTO Users (user_id, board_id, balance, active_items, posts_count) VALUES (?, ?, ?, ?, ?)",
                (attacker_id, board_id, 5000.0, json.dumps({"knife_gun": True}), 200)
            )

            # Target setup
            await db.execute(
                "INSERT OR REPLACE INTO Users (user_id, board_id, balance, active_items, posts_count) VALUES (?, ?, ?, ?, ?)",
                (target_id, board_id, 3000.0, '{}', newbie_posts)
            )

            fake_msg = MagicMock()
            fake_msg.from_user.id = attacker_id
            fake_msg.from_user.first_name = "Robber"
            fake_msg.chat = MagicMock(id=88888)
            fake_msg.reply_to_message = MagicMock()
            fake_msg.reply_to_message.from_user.id = target_id
            fake_msg.reply_to_message.message_id = 1234
            fake_msg.answer = AsyncMock()

            with patch("main.get_author_id_by_reply", new_callable=AsyncMock) as mock_auth:
                mock_auth.return_value = target_id
                await main.cmd_rob(fake_msg, board_id, stream="ru")

            # Check response
            fake_msg.answer.assert_called_once()
            ans_text = fake_msg.answer.call_args[0][0]
            assert "ИММУНИТЕТ НОВИЧКА" in ans_text, f"Failed for posts_count={newbie_posts}"
            assert "менее 50 постов" in ans_text

            # Target balance must NOT change
            target_bal = await db_mod.get_user_global_balance(db, target_id)
            assert target_bal == 3000.0

    @pytest.mark.asyncio
    async def test_cmd_rob_veteran_target_successful_theft_and_ledger(self, isolated_test_db):
        """
        Adversarial test: cmd_rob against target with posts_count = 50 (immunity threshold passed).
        1. Robbery succeeds.
        2. Target balance decreases, robber balance increases.
        3. UserTransactions records entries for BOTH target and robber under category 'rob'.
        """
        db = isolated_test_db
        attacker_id = 41001
        target_id = 41002
        board_id = "b"

        await db.execute(
            "INSERT OR REPLACE INTO Users (user_id, board_id, balance, active_items, posts_count) VALUES (?, ?, ?, ?, ?)",
            (attacker_id, board_id, 1000.0, json.dumps({"knife_gun": True}), 100)
        )
        await db.execute(
            "INSERT OR REPLACE INTO Users (user_id, board_id, balance, active_items, posts_count) VALUES (?, ?, ?, ?, ?)",
            (target_id, board_id, 5000.0, json.dumps({}), 50)
        )

        fake_msg = MagicMock()
        fake_msg.from_user.id = attacker_id
        fake_msg.from_user.first_name = "Robber"
        fake_msg.chat = MagicMock(id=88888)
        fake_msg.reply_to_message = MagicMock()
        fake_msg.reply_to_message.from_user.id = target_id
        fake_msg.reply_to_message.message_id = 1235
        fake_msg.answer = AsyncMock()
        fake_msg.bot = MagicMock()
        fake_msg.bot.send_message = AsyncMock()

        with patch("main.get_author_id_by_reply", new_callable=AsyncMock) as mock_auth:
            mock_auth.return_value = target_id
            # Force no deflection / miss
            with patch("random.random", return_value=0.99):
                with patch("random.uniform", return_value=0.20):  # 20% steal -> 1000 ₪
                    await main.cmd_rob(fake_msg, board_id, stream="ru")

        # Verify balances
        target_bal = await db_mod.get_user_global_balance(db, target_id)
        attacker_bal = await db_mod.get_user_global_balance(db, attacker_id)
        assert target_bal == 4000.0
        assert attacker_bal == 2000.0

        # Verify UserTransactions ledger records
        async with db.execute(
            "SELECT user_id, amount, category, description FROM UserTransactions WHERE category = 'rob' ORDER BY id ASC"
        ) as cur:
            txs = await cur.fetchall()

        assert len(txs) == 2, f"Expected 2 transaction entries, got: {txs}"
        # Target deduction
        assert txs[0][0] == target_id
        assert txs[0][1] == -1000.0
        assert txs[0][2] == "rob"
        assert "Тебя ограбил анон" in txs[0][3]

        # Robber gain
        assert txs[1][0] == attacker_id
        assert txs[1][1] == 1000.0
        assert txs[1][2] == "rob"
        assert "Успешное ограбление" in txs[1][3]

    @pytest.mark.asyncio
    async def test_cmd_rob_reflect_shield_balance_and_ledger(self, isolated_test_db):
        """
        Adversarial test: Target has active reflect_shield_until.
        Attacker's knife slips, attacker loses loss to victim, recorded in UserTransactions.
        """
        db = isolated_test_db
        attacker_id = 42001
        target_id = 42002
        board_id = "b"
        now = int(time.time())

        await db.execute(
            "INSERT OR REPLACE INTO Users (user_id, board_id, balance, active_items, posts_count) VALUES (?, ?, ?, ?, ?)",
            (attacker_id, board_id, 2000.0, json.dumps({"knife_gun": True}), 100)
        )
        await db.execute(
            "INSERT OR REPLACE INTO Users (user_id, board_id, balance, active_items, posts_count) VALUES (?, ?, ?, ?, ?)",
            (target_id, board_id, 1000.0, json.dumps({"reflect_shield_until": now + 3600}), 100)
        )

        fake_msg = MagicMock()
        fake_msg.from_user.id = attacker_id
        fake_msg.chat = MagicMock(id=88888)
        fake_msg.reply_to_message = MagicMock()
        fake_msg.reply_to_message.from_user.id = target_id
        fake_msg.answer = AsyncMock()
        fake_msg.bot = MagicMock()
        fake_msg.bot.send_message = AsyncMock()

        with patch("main.get_author_id_by_reply", new_callable=AsyncMock) as mock_auth:
            mock_auth.return_value = target_id
            with patch("random.random", return_value=0.99):
                with patch("random.uniform", return_value=0.25):  # 25% of attacker balance = 500
                    await main.cmd_rob(fake_msg, board_id, stream="ru")

        # Attacker lost 500, target gained 500
        attacker_bal = await db_mod.get_user_global_balance(db, attacker_id)
        target_bal = await db_mod.get_user_global_balance(db, target_id)
        assert attacker_bal == 1500.0
        assert target_bal == 1500.0

        # Verify UserTransactions
        async with db.execute(
            "SELECT user_id, amount, description FROM UserTransactions WHERE category = 'rob' ORDER BY id ASC"
        ) as cur:
            txs = await cur.fetchall()

        assert len(txs) == 2
        assert txs[0][0] == attacker_id and txs[0][1] == -500.0 and "Зеркало" in txs[0][2]
        assert txs[1][0] == target_id and txs[1][1] == 500.0 and "Зеркала" in txs[1][2]

    @pytest.mark.asyncio
    async def test_cmd_rob_pepperspray_defense_balance_and_ledger(self, isolated_test_db):
        """
        Adversarial test: Target has pepperspray_gun active.
        Robber is sprayed, loses 30% penalty (capped at 500 ₪) to victim, recorded in UserTransactions.
        """
        db = isolated_test_db
        attacker_id = 43001
        target_id = 43002
        board_id = "b"

        await db.execute(
            "INSERT OR REPLACE INTO Users (user_id, board_id, balance, active_items, posts_count) VALUES (?, ?, ?, ?, ?)",
            (attacker_id, board_id, 3000.0, json.dumps({"knife_gun": True}), 100)
        )
        await db.execute(
            "INSERT OR REPLACE INTO Users (user_id, board_id, balance, active_items, posts_count) VALUES (?, ?, ?, ?, ?)",
            (target_id, board_id, 1000.0, json.dumps({"pepperspray_gun": True}), 100)
        )

        fake_msg = MagicMock()
        fake_msg.from_user.id = attacker_id
        fake_msg.chat = MagicMock(id=88888)
        fake_msg.reply_to_message = MagicMock()
        fake_msg.reply_to_message.from_user.id = target_id
        fake_msg.answer = AsyncMock()
        fake_msg.bot = MagicMock()
        fake_msg.bot.send_message = AsyncMock()

        with patch("main.get_author_id_by_reply", new_callable=AsyncMock) as mock_auth:
            mock_auth.return_value = target_id
            with patch("random.random", return_value=0.99):
                with patch("random.uniform", return_value=0.20):
                    await main.cmd_rob(fake_msg, board_id, stream="ru")

        # Attacker lost capped 500 penalty, victim gained 500
        attacker_bal = await db_mod.get_user_global_balance(db, attacker_id)
        target_bal = await db_mod.get_user_global_balance(db, target_id)
        assert attacker_bal == 2500.0
        assert target_bal == 1500.0

        async with db.execute(
            "SELECT user_id, amount, description FROM UserTransactions WHERE category = 'rob' ORDER BY id ASC"
        ) as cur:
            txs = await cur.fetchall()

        assert len(txs) == 2
        assert txs[0][0] == attacker_id and txs[0][1] == -500.0 and "перцовкой" in txs[0][2]
        assert txs[1][0] == target_id and txs[1][1] == 500.0 and "перцовкой" in txs[1][2]

    @pytest.mark.asyncio
    async def test_cmd_rob_tinfoil_hat_damage_and_ledger(self, isolated_test_db):
        """
        Adversarial test: Target has tinfoil_hat active.
        Attacker cuts self on tinfoil, loses penalty to void/ground, recorded in UserTransactions.
        """
        db = isolated_test_db
        attacker_id = 44001
        target_id = 44002
        board_id = "b"
        now = int(time.time())

        await db.execute(
            "INSERT OR REPLACE INTO Users (user_id, board_id, balance, active_items, posts_count) VALUES (?, ?, ?, ?, ?)",
            (attacker_id, board_id, 2000.0, json.dumps({"knife_gun": True}), 100)
        )
        await db.execute(
            "INSERT OR REPLACE INTO Users (user_id, board_id, balance, active_items, posts_count) VALUES (?, ?, ?, ?, ?)",
            (target_id, board_id, 1000.0, json.dumps({"tinfoil_hat": now + 36000}), 100)
        )

        fake_msg = MagicMock()
        fake_msg.from_user.id = attacker_id
        fake_msg.chat = MagicMock(id=88888)
        fake_msg.reply_to_message = MagicMock()
        fake_msg.reply_to_message.from_user.id = target_id
        fake_msg.answer = AsyncMock()
        fake_msg.bot = MagicMock()
        fake_msg.bot.send_message = AsyncMock()

        with patch("main.get_author_id_by_reply", new_callable=AsyncMock) as mock_auth:
            mock_auth.return_value = target_id
            with patch("random.random", return_value=0.99):
                with patch("random.uniform", return_value=0.20):  # 20% of 2000 = 400
                    await main.cmd_rob(fake_msg, board_id, stream="ru")

        # Attacker lost 400
        attacker_bal = await db_mod.get_user_global_balance(db, attacker_id)
        assert attacker_bal == 1600.0

        async with db.execute(
            "SELECT user_id, amount, description FROM UserTransactions WHERE category = 'rob' ORDER BY id ASC"
        ) as cur:
            txs = await cur.fetchall()

        assert len(txs) == 1
        assert txs[0][0] == attacker_id and txs[0][1] == -400.0 and "фольги" in txs[0][2]

    @pytest.mark.asyncio
    async def test_all_combat_weapons_newbie_immunity(self, isolated_test_db):
        """
        Adversarial test: All 5 other combat weapons (/pepperspray, /shit, /vomit, /curse, /schizopill)
        must trigger newbie immunity against a target with posts < 50 and retain weapon in inventory.
        """
        db = isolated_test_db
        attacker_id = 45001
        target_id = 45002
        board_id = "b"

        # Attacker has all weapons
        all_guns = {
            "pepperspray_gun": True,
            "shit_gun": True,
            "vomit_gun": True,
            "laxative_gun": True,
            "schizopill_gun": True,
        }
        await db.execute(
            "INSERT OR REPLACE INTO Users (user_id, board_id, active_items, posts_count) VALUES (?, ?, ?, ?)",
            (attacker_id, board_id, json.dumps(all_guns), 100)
        )
        # Target is a newbie
        await db.execute(
            "INSERT OR REPLACE INTO Users (user_id, board_id, active_items, posts_count) VALUES (?, ?, '{}', 10)",
            (target_id, board_id)
        )

        weapons_to_test = [
            (main.cmd_pepperspray, "Перцовка осталась в твоем инвентаре"),
            (main.cmd_shit, "кусок говна остался при тебе"),
            (main.cmd_vomit, "блевота осталась при тебе"),
            (main.cmd_curse, "Слабительное осталось в твоем рюкзаке"),
            (main.cmd_schizopill, "Шизо-Таблетка осталась в твоем рюкзаке"),
        ]

        for cmd_func, expected_retention in weapons_to_test:
            # Clear combat state so each weapon tests immunity independently
            shared_state.reset_combat_state()
            fake_msg = MagicMock()
            fake_msg.from_user.id = attacker_id
            fake_msg.chat = MagicMock(id=88888)
            fake_msg.reply_to_message = MagicMock()
            fake_msg.reply_to_message.from_user.id = target_id
            fake_msg.answer = AsyncMock()

            with patch("main.get_author_id_by_reply", new_callable=AsyncMock) as mock_auth:
                mock_auth.return_value = target_id
                await cmd_func(fake_msg, board_id, stream="ru")

            fake_msg.answer.assert_called_once()
            ans_text = fake_msg.answer.call_args[0][0]
            assert "ИММУНИТЕТ НОВИЧКА" in ans_text
            assert expected_retention in ans_text

        # Attacker's active items MUST still have all weapons intact!
        attacker_items = await main._get_user_active_items(db, attacker_id, board_id)
        for gun_key in all_guns:
            assert attacker_items.get(gun_key) is True, f"Weapon {gun_key} was wrongly consumed!"

    @pytest.mark.asyncio
    async def test_target_grief_protection_blocks_repeat_attacks(self, isolated_test_db):
        """
        Adversarial test: Target attacked less than 5 minutes ago must be immune under grief protection.
        """
        attacker_id = 46001
        target_id = 46002
        board_id = "b"

        # Register attack on target
        shared_state.register_target_attack(target_id)
        assert shared_state.get_target_grief_protection_remaining(target_id) > 290

        fake_msg = MagicMock()
        fake_msg.from_user.id = attacker_id
        fake_msg.answer = AsyncMock()

        # check_target_grief_protection must return True and send notification
        is_blocked = await check_target_grief_protection(fake_msg, target_id, attacker_id, board_id)
        assert is_blocked is True
        fake_msg.answer.assert_called_once()
        assert "ИММУНИТЕТ ЦЕЛИ ОТ ГРИФЕРСТВА" in fake_msg.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_cross_board_posts_count_and_fallback(self, isolated_test_db):
        """
        Adversarial test:
        1. User has 25 posts on /b/ and 30 posts on /vg/ in Users table -> total 55 >= 50 (not newbie).
        2. User has 0 in Users.posts_count, but 55 rows in Posts table -> fallback to Posts table resolves 55.
        """
        db = isolated_test_db
        uid_1 = 47001
        uid_2 = 47002

        # Ensure board 'vg' exists in Boards
        await db.execute("INSERT OR IGNORE INTO Boards (board_id, name) VALUES ('vg', 'vg')")

        # 1. Multi-board rows in Users
        await db.execute("INSERT INTO Users (user_id, board_id, posts_count) VALUES (?, 'b', 25)", (uid_1,))
        await db.execute("INSERT INTO Users (user_id, board_id, posts_count) VALUES (?, 'vg', 30)", (uid_1,))

        cnt_1 = await get_user_posts_count(db, uid_1)
        assert cnt_1 == 55
        assert await is_newbie(db, uid_1) is False

        # 2. Legacy user with 0 in Users, but 55 rows in Posts table
        await db.execute("INSERT INTO Users (user_id, board_id, posts_count) VALUES (?, 'b', 0)", (uid_2,))
        for pnum in range(1, 56):
            await db.execute(
                "INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (?, 'b', ?, ?, 1700000)",
                (pnum, uid_2, json.dumps({"text": "hi"}))
            )

        cnt_2 = await get_user_posts_count(db, uid_2)
        assert cnt_2 == 55
        assert await is_newbie(db, uid_2) is False


# =============================================================================
# PART 3: ECONOMY & BANK TAXES ADVERSARIAL CHALLENGES
# =============================================================================

class TestEconomyAndBankTaxes:
    """Stress-test _do_tax with active dynamic bank deposits and persistent daily limits."""

    @pytest.fixture(autouse=True)
    def clean_daily_limits(self):
        shared_state._DAILY_SHOP_PURCHASES.clear()
        yield
        shared_state._DAILY_SHOP_PURCHASES.clear()

    @pytest.mark.asyncio
    async def test_wealth_tax_dynamic_interest_accrued_and_taxed_accurately(self, isolated_test_db):
        """
        Adversarial test:
        - User has 0 wallet balance.
        - Active bank deposit of 200,000 ₪ principal with 2.5% daily rate.
        - Created 4 days ago (345,600s).
        - Dynamic interest = 200,000 * 0.025 * 4 = +20,000 ₪.
        - Total taxable wealth = 220,000 ₪.
        - Static tax query would evaluate only 200,000 -> tax = 1,635 ₪.
        - Dynamic tax query evaluates 220,000 -> tax = 1,835 ₪.
        - Verifies that:
          1. Exactly 1,835 ₪ is calculated and deducted from the deposit.
          2. Deposit's accrued_interest and last_accrual_at are crystallized.
          3. UserTransactions records the tax deduction with '[из банка: 1,835 ₪]'.
        """
        db = isolated_test_db
        uid = 50001
        base_ts = 1788000000.0
        now_ts = base_ts + 4 * 86400.0

        await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 0.0)", (uid,))
        await db.execute("""
            INSERT INTO BankDeposits (
                user_id, board_id, tier_id, principal, daily_rate, created_at,
                locked_until, last_accrual_at, accrued_interest, status
            ) VALUES (?, 'b', 'skuf', 200000.0, 0.025, ?, ?, ?, 0.0, 'active')
        """, (uid, base_ts, base_ts + 86400, base_ts))
        await db.commit()

        # Expected taxes
        tax_static = db_mod.calculate_daily_wealth_tax(200000.0)
        tax_dynamic = db_mod.calculate_daily_wealth_tax(220000.0)
        assert tax_static == 1635.0
        assert tax_dynamic == 1835.0

        affected, confiscated, details = await db_mod.apply_daily_wealth_tax(db, current_ts=now_ts)

        assert affected == 1
        assert confiscated == 1835.0

        # Verify BankDeposit state was updated and crystallized
        async with db.execute(
            "SELECT principal, accrued_interest, last_accrual_at FROM BankDeposits WHERE user_id = ?",
            (uid,)
        ) as cur:
            row = await cur.fetchone()

        princ, accr, last_accr = row
        # Principal was deducted: 200000 - 1835 = 198165.0
        assert princ == 198165.0
        # Accrued interest was crystallized: 20000.0
        assert accr == 20000.0
        assert last_accr == now_ts

        # Verify UserTransactions
        async with db.execute(
            "SELECT amount, description FROM UserTransactions WHERE user_id = ?",
            (uid,)
        ) as cur:
            tx = await cur.fetchone()

        assert tx is not None
        assert tx[0] == -1835.0
        assert "[из банка: 1,835 ₪]" in tx[1]

    @pytest.mark.asyncio
    async def test_wealth_tax_deposit_only_user_without_users_row(self, isolated_test_db):
        """
        Adversarial test: User has an active bank deposit of 50,000 ₪, but NO row in Users table.
        The CTE with all_uids (UNION) must still discover and tax this user!
        """
        db = isolated_test_db
        uid = 50002
        base_ts = 1788000000.0

        await db.execute("""
            INSERT INTO BankDeposits (
                user_id, board_id, tier_id, principal, daily_rate, created_at,
                locked_until, last_accrual_at, accrued_interest, status
            ) VALUES (?, 'b', 'safe', 50000.0, 0.005, ?, ?, ?, 0.0, 'active')
        """, (uid, base_ts, base_ts + 86400, base_ts))
        await db.commit()

        # 50,000 ₪ wealth -> tax = (50,000 - 5,000) * 0.003 = 135.0 ₪
        affected, confiscated, details = await db_mod.apply_daily_wealth_tax(db, current_ts=base_ts)
        assert affected == 1
        assert confiscated == 135.0

    @pytest.mark.asyncio
    async def test_wealth_tax_exempt_poor_users(self, isolated_test_db):
        """Users with total wealth <= 5,000 ₪ must have exactly 0 tax."""
        db = isolated_test_db
        uid = 50003
        base_ts = 1788000000.0

        await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 5000.0)", (uid,))
        affected, confiscated, _ = await db_mod.apply_daily_wealth_tax(db, current_ts=base_ts)
        assert affected == 0
        assert confiscated == 0.0

    @pytest.mark.asyncio
    async def test_daily_limits_persistence_across_simulated_db_reboot(self, isolated_test_db):
        """
        Adversarial test:
        1. User buys 35 gold safes (limit is 40/day) recorded into UserDailyLimits table.
        2. Simulated reboot: in-memory _DAILY_SHOP_PURCHASES cache is wiped.
        3. sync_daily_limits_from_db is called.
        4. In-memory cache is fully restored, aliases ('gold', 'gold_safe', 'lootbox_gold') are populated.
        5. User cannot purchase 6 more (would exceed 40), but can purchase 5 more.
        """
        db = isolated_test_db
        uid = 50004
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # 1. Record 35 purchases of gold lootbox
        count = await db_mod.record_user_daily_limit(db, uid, "lootbox_gold", day_date=today, increment=35)
        assert count == 35

        # 2. Simulate complete bot crash / reboot
        shared_state._DAILY_SHOP_PURCHASES.clear()
        assert len(shared_state._DAILY_SHOP_PURCHASES) == 0

        # 3. Startup hydration
        synced = await db_mod.sync_daily_limits_from_db(db, day_date=today)
        assert synced >= 1

        # 4. Verify in-memory state restored across all aliases
        assert shared_state.get_user_daily_shop_buys(uid, "lootbox_gold") == 35
        assert shared_state.get_user_daily_shop_buys(uid, "gold_safe") == 35
        assert shared_state.get_user_daily_shop_buys(uid, "gold") == 35

        # 5. Check limits:
        assert lootbox_engine.can_open_lootbox(uid, "gold_safe") is True  # 35 < 40
        allowed, cur_cnt, max_cnt = shared_state.check_shop_purchase_limit(uid, "gold_safe")
        assert allowed is True
        assert cur_cnt == 35

        # Simulate buying 5 more -> reaches 40
        await db_mod.record_user_daily_limit(db, uid, "lootbox_gold", day_date=today, increment=5)
        await db_mod.sync_daily_limits_from_db(db, day_date=today)
        assert shared_state.get_user_daily_shop_buys(uid, "gold_safe") == 40

        # Limit reached: cannot open or buy more
        assert lootbox_engine.can_open_lootbox(uid, "gold_safe") is False
        allowed, cur_cnt, max_cnt = shared_state.check_shop_purchase_limit(uid, "gold_safe")
        assert allowed is False
        assert cur_cnt == 40


# =============================================================================
# PART 4: AI PERSONA & MUSIC ROAST ADVERSARIAL CHALLENGES
# =============================================================================

class TestAIPersonaAndMusicRoast:
    """Challenge Cyberchad rate-limit rejection suppression, Block 2 context, and Music Roast scores."""

    def test_cyberchad_self_roast_suppression_predicates(self):
        """
        Adversarial test: All known rate-limit rejection phrases and markers
        must be strictly detected by is_rate_limit_rejection_post.
        """
        for phrase in router_mod.CYBERCHAD_RATE_LIMIT_REJECTIONS:
            # As text dict
            assert router_mod.is_rate_limit_rejection_post({"text": phrase}) is True, f"Failed for: {phrase}"
            # As transcription
            assert router_mod.is_rate_limit_rejection_post({"transcription": phrase}) is True
            # As JSON string content
            assert router_mod.is_rate_limit_rejection_post({"content": json.dumps({"text": phrase})}) is True
            # With 'е' substituted for 'ё'
            phrase_e = phrase.replace("ё", "е")
            assert router_mod.is_rate_limit_rejection_post({"text": phrase_e}) is True

        # Marker substrings
        markers = [
            "лимит на нытьё", "минутный кулдаун", "забейся под шконку на минуту",
            "один высер в шестьдесят секунд", "шестьдесят секунд"
        ]
        for marker in markers:
            assert router_mod.is_rate_limit_rejection_post({"text": f"Слышь ты, {marker}, понял?"}) is True

        # Legitimate user post must NOT be flagged as rate limit rejection
        assert router_mod.is_rate_limit_rejection_post({"text": "Привет Киберчед, поясни за рэпчик"}) is False

    @pytest.mark.asyncio
    async def test_is_rate_limit_rejection_target_with_voice_transcription_db(self, isolated_test_db):
        """
        Adversarial test: An offline voice note rejection post in DB has only a file_id,
        and its transcription was saved into VoiceTranscriptions.
        is_rate_limit_rejection_target must query VoiceTranscriptions and recognize it!
        """
        db = isolated_test_db
        pnum = 60001
        fid = "voice_file_rejection_999"
        rejection_text = "Завали ебало, спамер хуев. У тебя лимит на нытьё — минута."

        # Create VoiceTranscriptions table in isolated test db
        await db.execute("""
            CREATE TABLE IF NOT EXISTS VoiceTranscriptions (
                file_id TEXT PRIMARY KEY,
                transcription TEXT,
                duration REAL,
                created_at REAL
            )
        """)

        # Insert into Posts
        await db.execute(
            "INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (?, 'b', 0, ?, ?)",
            (pnum, json.dumps({"type": "voice", "file_id": fid}), time.time())
        )
        # Insert into VoiceTranscriptions
        await db.execute(
            "INSERT INTO VoiceTranscriptions (file_id, transcription, duration) VALUES (?, ?, 5.0)",
            (fid, rejection_text)
        )
        await db.commit()

        # is_rate_limit_rejection_target must return True
        is_rej = await router_mod.is_rate_limit_rejection_target(pnum)
        assert is_rej is True

    @pytest.mark.asyncio
    async def test_block2_context_differentiation_grandparent_author(self):
        """
        Adversarial test:
        - User A (id 1111) sent an empty voice note in post >>500.
        - Cyberchad (author_id 0) roasted User A in post >>501 ("Хули ты мне тишину прислал?").
        - User B (id 2222) replied to Cyberchad in post >>502 ("Киберчед, ты че быкуешь на него?").
        - When building context for post >>502, Block 2 MUST detect that User B is a THIRD-PARTY OBSERVER,
          and MUST NOT conflate User A's silence with User B.
        """
        import ai_manager

        user_a_id = 111111
        user_b_id = 222222
        post_500 = 500
        post_501 = 501
        post_502 = 502

        # Populate storage
        async with ai_manager.storage_lock:
            ai_manager.messages_storage[post_500] = {
                'post_num': post_500,
                'board_id': 'b',
                'author_id': user_a_id,
                'content': {'type': 'voice', 'text': '[Тишина]'},
                'timestamp': 1000.0,
            }
            ai_manager.messages_storage[post_501] = {
                'post_num': post_501,
                'board_id': 'b',
                'author_id': 0,
                'reply_to_post_num': post_500,
                'content': {'text': 'Хули ты мне тишину прислал, глухонемой?'},
                'timestamp': 1005.0,
            }
            ai_manager.messages_storage[post_502] = {
                'post_num': post_502,
                'board_id': 'b',
                'author_id': user_b_id,
                'reply_to_post_num': post_501,
                'content': {'text': 'Киберчед, ты че быкуешь на него?'},
                'timestamp': 1010.0,
            }

        # Build context for User B replying to post 501 with limits=0 to avoid DB queries
        prompt = await ai_manager.build_cyberchad_context(
            board_id='b',
            target_post_num=post_502,
            author_id=user_b_id,
            limit_board=0,
            limit_author=0,
            limit_chad=0
        )

        # Prompt must contain the explicit third-party observer warning!
        assert "СТОРОННИЙ НАБЛЮДАТЕЛЬ/КОММЕНТАТОР" in prompt
        assert f"НЕ автор исходного поста >>{post_500}" in prompt
        assert "КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО приписывать" in prompt

    def test_music_roast_scale_boundary_scores(self):
        """
        Adversarial test: Music Roast score formatting and semantic normalization:
        - 0/10 with positive diagnosis: preserved as 0/10 💩.
        - 10/10 with negative diagnosis: preserved as 10/10 💩.
        - 0/10 with negative diagnosis (oxymoron): inverted to 10/10 💩.
        - 10/10 with positive diagnosis (oxymoron): inverted to 0/10 💩.
        - Oxymoron text replacement: 'шедевр мочи' -> 'тотальный зашквар'.
        - Duplicate suffix stripping: '/10 💩/10 💩'.
        - Fallbacks for None, empty, malformed strings.
        """
        import ai_manager

        # 1. Clean boundary scores
        clean_0 = ai_manager.format_music_rating_display("0/10 💩 (Эталонный чистый вкус)")
        assert "0/10 💩" in clean_0
        assert "Эталонный чистый вкус" in clean_0

        clean_10 = ai_manager.format_music_rating_display("10/10 💩 (Тотальный зашквар и помойка)")
        assert "10/10 💩" in clean_10

        # 2. Semantic inversion (LLM erroneously scored 0/10 for terrible music)
        inv_0_to_10 = ai_manager.format_music_rating_display("0/10 💩 (Уши кровоточат, блевотный кал)")
        assert "10/10 💩" in inv_0_to_10
        assert "Уши кровоточат" in inv_0_to_10

        # Semantic inversion (LLM erroneously scored 10/10 for god-tier music)
        inv_10_to_0 = ai_manager.format_music_rating_display("10/10 💩 (Шедевр без говна, чистый вкус)")
        assert "0/10 💩" in inv_10_to_0

        # 3. Oxymorons
        oxymoron_1 = ai_manager.format_music_rating_display("0/10 💩 (Шедевр мочи)/10 💩")
        assert "10/10 💩" in oxymoron_1
        assert "тотальный зашквар" in oxymoron_1

        oxymoron_2 = ai_manager.format_music_rating_display("0/10 (Даже бомжи на помойке не слушают)")
        assert "10/10 💩" in oxymoron_2

        # 4. Suffix deduplication
        dedup_1 = ai_manager.format_music_rating_display("8/10 💩 (Диагноз)/10 💩")
        assert dedup_1 == "8/10 💩 (Диагноз)"

        dedup_2 = ai_manager.format_music_rating_display("7/10 💩 (Кринж) /10 💩")
        assert dedup_2 == "7/10 💩 (Кринж)"

        dedup_3 = ai_manager.format_music_rating_display("9/10 💩 (Диагноз /10 💩)")
        assert dedup_3 == "9/10 💩 (Диагноз)"

        # 5. Invalid / empty fallback
        fallback_none = ai_manager.format_music_rating_display(None)
        assert fallback_none == "10/10 💩 (Тотальный зашквар и помойный кал)"

        fallback_empty = ai_manager.format_music_rating_display("")
        assert fallback_empty == "10/10 💩 (Тотальный зашквар и помойный кал)"
