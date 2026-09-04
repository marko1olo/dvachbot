# -*- coding: utf-8 -*-
"""
tests/test_combat_moderation_system.py
======================================
Comprehensive test suite for the overhauled /partyvan and /shoot systems:
- Progressive mute durations based on 24h frequency
- Hard newbie immunity (posts_count < 25)
- Active user resistance multipliers (posts >= 1000, 250, 50)
- Misfire and backfire escalation
- Community appeal mechanics (3 votes -> unmute + fine)
- Instant bail / bribe mechanics
- Single-pair grief cooldown
"""

import time
import json
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite

import combat_moderation_engine as cme
from combat_moderation_engine import (
    calculate_combat_duration_and_backfire,
    record_combat_attack,
    get_attacker_24h_usage_count,
    check_pair_attack_cooldown,
    create_combat_appeal_session,
    get_combat_appeal_keyboard,
    active_combat_appeals,
    reset_combat_moderation_state,
    callback_combat_appeal,
    callback_combat_bail,
    APPEAL_VOTES_REQUIRED,
    ATTACKER_FALSE_REPORT_FINE
)


class TestCombatModerationFormulas(unittest.TestCase):
    def setUp(self):
        reset_combat_moderation_state()

    def test_progressive_partyvan_durations(self):
        attacker = 1001
        target = 2001

        # 1st call: 6 hours (21600s), 0% backfire (target has 300 posts -> standard)
        with patch('random.random', return_value=0.5):
            dur1, backfire1, _ = calculate_combat_duration_and_backfire(attacker, target, "partyvan", target_posts=300)
            self.assertEqual(dur1, 21600)
            self.assertFalse(backfire1)

        record_combat_attack(attacker, target, "partyvan")

        # 2nd call: 3 hours (10800s), 15% backfire
        with patch('random.random', return_value=0.5):
            dur2, backfire2, _ = calculate_combat_duration_and_backfire(attacker, target, "partyvan", target_posts=300)
            self.assertEqual(dur2, 10800)
            self.assertFalse(backfire2)

        record_combat_attack(attacker, target, "partyvan")

        # 3rd call: 1.5 hours (5400s), 40% backfire
        with patch('random.random', return_value=0.5):
            dur3, backfire3, _ = calculate_combat_duration_and_backfire(attacker, target, "partyvan", target_posts=300)
            self.assertEqual(dur3, 5400)
            self.assertFalse(backfire3)

        record_combat_attack(attacker, target, "partyvan")

        # 4th call: 1 hour (3600s), 75% backfire
        with patch('random.random', return_value=0.9):
            dur4, backfire4, _ = calculate_combat_duration_and_backfire(attacker, target, "partyvan", target_posts=300)
            self.assertEqual(dur4, 3600)
            self.assertFalse(backfire4)

    def test_progressive_shoot_durations(self):
        attacker = 1002
        target = 2002

        # 1st shot: 15 min (900s)
        dur1, backfire1, _ = calculate_combat_duration_and_backfire(attacker, target, "shoot", target_posts=300)
        self.assertEqual(dur1, 900)
        self.assertFalse(backfire1)

        record_combat_attack(attacker, target, "shoot")

        # 2nd shot: 10 min (600s)
        with patch('random.random', return_value=0.5):
            dur2, backfire2, _ = calculate_combat_duration_and_backfire(attacker, target, "shoot", target_posts=300)
            self.assertEqual(dur2, 600)
            self.assertFalse(backfire2)

        record_combat_attack(attacker, target, "shoot")

        # 3rd shot: 5 min (300s)
        with patch('random.random', return_value=0.5):
            dur3, backfire3, _ = calculate_combat_duration_and_backfire(attacker, target, "shoot", target_posts=300)
            self.assertEqual(dur3, 300)
            self.assertFalse(backfire3)

        record_combat_attack(attacker, target, "shoot")

        # 4th shot: 1 min (60s)
        with patch('random.random', return_value=0.9):
            dur4, backfire4, _ = calculate_combat_duration_and_backfire(attacker, target, "shoot", target_posts=300)
            self.assertEqual(dur4, 60)
            self.assertFalse(backfire4)

    def test_victim_activity_resistance_flipped(self):
        attacker = 1003
        target = 2003

        # Base 1st partyvan = 21600s (6h)
        # posts_count < 50 -> полный отлёт атаки (0s)
        dur_newbie, _, _ = calculate_combat_duration_and_backfire(attacker, target, "partyvan", target_posts=40)
        self.assertEqual(dur_newbie, 0)

        # 50 <= posts_count < 250 -> -30% (15120s)
        dur_mid, _, _ = calculate_combat_duration_and_backfire(attacker, target, "partyvan", target_posts=100)
        self.assertEqual(dur_mid, 15120)

        # posts_count >= 250 -> стандартное время без поблажек (21600s)
        dur_exp, _, _ = calculate_combat_duration_and_backfire(attacker, target, "partyvan", target_posts=500)
        self.assertEqual(dur_exp, 21600)

    def test_partyvan_flavor_text(self):
        from combat_moderation_engine import get_partyvan_flavor_text
        self.assertIn("ОМОН", get_partyvan_flavor_text(0))
        self.assertIn("3 часов", get_partyvan_flavor_text(1))
        self.assertIn("1.5 часа", get_partyvan_flavor_text(2))
        self.assertIn("1 час", get_partyvan_flavor_text(3))

    def test_backfire_trigger(self):
        attacker = 1004
        target = 2004

        # Simulate 2 prior attacks
        record_combat_attack(attacker, target, "partyvan")
        record_combat_attack(attacker, target, "partyvan")

        # 3rd attack has 40% backfire chance. If roll < 0.40 -> triggers backfire!
        with patch('random.random', return_value=0.20):
            dur, is_backfire, chance = calculate_combat_duration_and_backfire(attacker, target, "partyvan", target_posts=10)
            self.assertTrue(is_backfire)
            self.assertEqual(dur, 0)
            self.assertEqual(chance, 0.40)

    def test_pair_attack_cooldown(self):
        attacker = 1005
        target = 2005

        # Before attack: allowed
        blocked, _ = check_pair_attack_cooldown(attacker, target)
        self.assertFalse(blocked)

        record_combat_attack(attacker, target, "shoot")

        # Immediately after: blocked for 15 minutes (900s)
        blocked, rem = check_pair_attack_cooldown(attacker, target)
        self.assertTrue(blocked)
        self.assertTrue(890 <= rem <= 900)

        # Different target: allowed!
        blocked_diff, _ = check_pair_attack_cooldown(attacker, 9999)
        self.assertFalse(blocked_diff)


class TestCombatAppealAndBail(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        reset_combat_moderation_state()
        self.db = await aiosqlite.connect(":memory:")
        await self.db.execute("""
            CREATE TABLE Users (
                user_id INTEGER,
                board_id TEXT,
                balance REAL,
                posts_count INTEGER
            )
        """)
        await self.db.commit()

        self.patch_pool = patch('combat_moderation_engine.get_pool', return_value=self.db)
        self.patch_pool.start()

    async def asyncTearDown(self):
        self.patch_pool.stop()
        await self.db.close()

    async def test_appeal_voting_flow(self):
        attacker_id = 111
        target_id = 222
        voter1 = 331
        voter2 = 332
        voter3 = 333

        # Populate users
        for uid in [voter1, voter2, voter3]:
            await self.db.execute("INSERT INTO Users VALUES (?, 'b', 1000.0, 50)", (uid,))
        await self.db.execute("INSERT INTO Users VALUES (?, 'b', 5000.0, 500)", (attacker_id,))
        await self.db.commit()

        sess_id = create_combat_appeal_session("b", attacker_id, target_id, "partyvan", 7200)

        # 1. Attacker attempts to vote -> rejected
        cb_attacker = MagicMock()
        cb_attacker.from_user.id = attacker_id
        cb_attacker.data = f"cappeal:{sess_id}"
        cb_attacker.answer = AsyncMock()
        await callback_combat_appeal(cb_attacker)
        cb_attacker.answer.assert_called_with("🚫 Доносчик не может голосовать за отмену собственного доноса!", show_alert=True)

        # 2. Target attempts to vote -> rejected
        cb_target = MagicMock()
        cb_target.from_user.id = target_id
        cb_target.data = f"cappeal:{sess_id}"
        cb_target.answer = AsyncMock()
        await callback_combat_appeal(cb_target)
        cb_target.answer.assert_called_with("🚫 Жертва не может голосовать сама за себя! Нужна поддержка других анонов треда.", show_alert=True)

        # 3. Voter 1 votes -> accepted (1/3)
        cb_v1 = MagicMock()
        cb_v1.from_user.id = voter1
        cb_v1.data = f"cappeal:{sess_id}"
        cb_v1.answer = AsyncMock()
        cb_v1.message.edit_reply_markup = AsyncMock()
        await callback_combat_appeal(cb_v1)
        cb_v1.answer.assert_called_with(f"⚖️ Твой протест учтен (1/{APPEAL_VOTES_REQUIRED})!", show_alert=False)

        # 4. Voter 1 votes again -> duplicate rejected
        await callback_combat_appeal(cb_v1)
        cb_v1.answer.assert_called_with("⚠️ Ты уже отдал свой голос за отмену этого мута!", show_alert=False)

        # 5. Voter 2 votes -> accepted (2/3)
        cb_v2 = MagicMock()
        cb_v2.from_user.id = voter2
        cb_v2.data = f"cappeal:{sess_id}"
        cb_v2.answer = AsyncMock()
        cb_v2.message.edit_reply_markup = AsyncMock()
        await callback_combat_appeal(cb_v2)
        cb_v2.answer.assert_called_with(f"⚖️ Твой протест учтен (2/{APPEAL_VOTES_REQUIRED})!", show_alert=False)

        # 6. Voter 3 votes -> threshold reached (3/3)!
        cb_v3 = MagicMock()
        cb_v3.from_user.id = voter3
        cb_v3.data = f"cappeal:{sess_id}"
        cb_v3.answer = AsyncMock()
        cb_v3.message.edit_text = AsyncMock()

        with patch('common.bot_helpers.remove_regular_mute', new_callable=AsyncMock) as mock_unmute, \
             patch('main.deduct_user_global_balance', new_callable=AsyncMock) as mock_fine:
            await callback_combat_appeal(cb_v3)

            # Target must be unmuted!
            mock_unmute.assert_called_once_with(target_id, "b")
            # Attacker must be fined 500₪!
            mock_fine.assert_called_once_with(self.db, attacker_id, "b", ATTACKER_FALSE_REPORT_FINE)
            # Announcement message edited
            cb_v3.message.edit_text.assert_called_once()
            self.assertIn("МУТ АННУЛИРОВАН ОБЩЕСТВОМ", cb_v3.message.edit_text.call_args[0][0])
            from shared_state import get_partyvan_victim_immunity
            self.assertGreater(get_partyvan_victim_immunity(target_id), time.time())

    async def test_bail_payment_flow(self):
        attacker_id = 111
        target_id = 222
        payer_id = 333  # Friend bailing out target

        await self.db.execute("INSERT INTO Users VALUES (?, 'b', 1500.0, 20)", (payer_id,))
        await self.db.commit()

        sess_id = create_combat_appeal_session("b", attacker_id, target_id, "partyvan", 7200)

        cb_payer = MagicMock()
        cb_payer.from_user.id = payer_id
        cb_payer.data = f"cbail:{sess_id}"
        cb_payer.answer = AsyncMock()
        cb_payer.message.edit_text = AsyncMock()

        with patch('main.get_current_item_price', return_value=600.0, create=True), \
             patch('main.remove_regular_mute', new_callable=AsyncMock) as mock_unmute, \
             patch('main.deduct_user_global_balance', new_callable=AsyncMock) as mock_deduct:
            await callback_combat_bail(cb_payer)

            mock_deduct.assert_called_once_with(self.db, payer_id, "b", 600.0)
            mock_unmute.assert_called_once_with(target_id, "b")
            cb_payer.message.edit_text.assert_called_once()
            self.assertIn("ВЫКУП ИЗ-ПОД АРЕСТА", cb_payer.message.edit_text.call_args[0][0])
            from shared_state import get_partyvan_victim_immunity
            self.assertGreater(get_partyvan_victim_immunity(target_id), time.time())


if __name__ == '__main__':
    unittest.main()
