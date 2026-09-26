import asyncio
import os
import sys
import time
from datetime import datetime, timezone
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import shared_state
from bank_engine import build_bank_dashboard_view, BANK_TIERS
from main import get_current_item_price


class TestVoiceAndBankFixes(unittest.IsolatedAsyncioTestCase):
    def test_bank_dashboard_view_length_under_950_chars(self):
        """Even with 10 deposits, dashboard text must never exceed 950 characters."""
        deposits = []
        for i in range(1, 11):
            tier = "sych" if i % 3 == 0 else ("skuf" if i % 3 == 1 else "mmm_abu")
            deposits.append({
                "id": 100 + i,
                "tier_id": tier,
                "short_name": BANK_TIERS[tier]["short_name"],
                "principal": float(1000 * i),
                "accrued_interest": float(123.45 * i),
                "is_locked": (i % 2 == 0),
                "remaining_lock_sec": 3600 * i if (i % 2 == 0) else 0,
            })

        text, kb = build_bank_dashboard_view(
            wallet_balance=1234567.89,
            total_principal=550000.0,
            total_accrued=12345.67,
            deposits=deposits
        )

        self.assertLessEqual(len(text), 950, f"Dashboard text exceeded limit: {len(text)} chars")
        # Check buttons
        button_callbacks = [b.callback_data for row in kb.inline_keyboard for b in row]
        self.assertIn("bank_deposit_menu", button_callbacks)
        self.assertIn("bank_withdraw_menu", button_callbacks)
        self.assertIn("bank_refresh", button_callbacks)

    def test_mute_gun_escalating_price(self):
        """Mute gun pricing escalates with purchases today: 500 -> 1500 -> 3500."""
        user_id = 888123
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # 0 purchases
        shared_state._DAILY_SHOP_PURCHASES[(user_id, "mute", today_str)] = 0
        p0 = get_current_item_price("mute", user_id=user_id)
        self.assertEqual(p0, 500)

        # 1 purchase
        shared_state._DAILY_SHOP_PURCHASES[(user_id, "mute", today_str)] = 1
        p1 = get_current_item_price("mute", user_id=user_id)
        self.assertEqual(p1, 1500)

        # 2 purchases
        shared_state._DAILY_SHOP_PURCHASES[(user_id, "mute", today_str)] = 2
        p2 = get_current_item_price("mute", user_id=user_id)
        self.assertEqual(p2, 3500)

    def test_mute_gun_daily_limit_is_three(self):
        """Mute gun daily limit is strictly 3."""
        user_id = 888456
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        self.assertEqual(shared_state.SHOP_DAILY_LIMITS.get("mute"), 3)

        shared_state._DAILY_SHOP_PURCHASES[(user_id, "mute", today_str)] = 2
        allowed, cur, lim = shared_state.check_shop_purchase_limit(user_id, "mute")
        self.assertTrue(allowed)
        self.assertEqual(lim, 3)

        shared_state._DAILY_SHOP_PURCHASES[(user_id, "mute", today_str)] = 3
        allowed, cur, lim = shared_state.check_shop_purchase_limit(user_id, "mute")
        self.assertFalse(allowed)

    def test_grief_protection_duration(self):
        """Grief protection defaults to 2700 seconds (45 minutes)."""
        target_id = 999888
        shared_state.register_target_attack(target_id)
        rem = shared_state.get_target_grief_protection_remaining(target_id)
        self.assertGreaterEqual(rem, 2690)
        self.assertLessEqual(rem, 2700)

    async def test_persistent_victim_immunity(self):
        """Victim immunity persists in SQLite and can be hydrated on restart."""
        import aiosqlite
        from common.database import record_user_immunity, sync_user_immunity_from_db

        async with aiosqlite.connect(":memory:") as db:
            await db.execute("""
            CREATE TABLE IF NOT EXISTS UserImmunity (
                user_id INTEGER NOT NULL,
                immunity_type TEXT NOT NULL,
                expires_at REAL NOT NULL,
                PRIMARY KEY (user_id, immunity_type)
            );
            """)
            await db.commit()

            target_id = 777999
            exp_ts = time.time() + 3600

            # Record immunity to DB
            await record_user_immunity(db, target_id, "partyvan", exp_ts)

            # Clear in-memory cache to simulate cold process restart
            shared_state._VICTIM_PARTYVAN_IMMUNITY.pop(target_id, None)
            self.assertEqual(shared_state.get_partyvan_victim_immunity(target_id), 0.0)

            # Hydrate from DB
            synced = await sync_user_immunity_from_db(db)
            self.assertEqual(synced, 1)
            self.assertAlmostEqual(shared_state.get_partyvan_victim_immunity(target_id), exp_ts, places=1)


if __name__ == "__main__":
    unittest.main()
