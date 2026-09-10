# -*- coding: utf-8 -*-
"""
verification_scripts/verify_tax_raid_shop_adversarial.py
Standalone empirical verification runner for challenger_m3_gen3_2:
- Super-Wealth Tax progression & idle surcharge
- /raid_oligarch sybil, gear defenses & confiscation math
- M2 Shop non-buyable relic guard
"""

import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure root dvachbot directory is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import aiosqlite
import common.config
import common.database
import common.db_pool
from main import cb_shop_buy
from wardrobe_engine import CLOTHING_CATALOG
from whale_economy_engine import (
    calculate_wealth_tax,
    execute_oligarch_raid,
    process_daily_wealth_tax,
)


class VerificationSummary:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.results = []

    def check(self, name: str, condition: bool, details: str = ""):
        if condition:
            self.passed += 1
            print(f"  [PASS] {name}" + (f" -> {details}" if details else ""))
            self.results.append((name, True, details))
        else:
            self.failed += 1
            print(f"  [FAIL] {name}" + (f" -> {details}" if details else ""))
            self.results.append((name, False, details))


async def create_isolated_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name

    db = await aiosqlite.connect(db_path)
    await db.execute("PRAGMA journal_mode=WAL;")
    await common.database._create_tables(db)
    await common.database._apply_migrations(db)
    return db, db_path


async def run_all_checks():
    summary = VerificationSummary()
    print("=" * 75)
    print("EMPIRICAL ADVERSARIAL VERIFICATION: TAX, RAID & SHOP RELICS")
    print("=" * 75)

    # -------------------------------------------------------------------------
    # 1. WEALTH TAX PROGRESSION & IDLE SURCHARGE
    # -------------------------------------------------------------------------
    print("\n--- SECTION 1: SUPER-WEALTH TAX BRACKETS & IDLE SURCHARGE ---")

    # Tier 0 (<= 5,000 ₪) -> 0%
    summary.check("Tax Tier 0 (0 ₪)", calculate_wealth_tax(0.0) == 0.0, "Tax = 0.0")
    summary.check("Tax Tier 0 (5,000 ₪)", calculate_wealth_tax(5000.0) == 0.0, "Tax = 0.0")
    summary.check("Tax Negative (-500 ₪)", calculate_wealth_tax(-500.0) == 0.0, "Tax = 0.0")

    # Tier 1 (5,001 - 50,000 ₪) -> 0.3%
    t_5001 = calculate_wealth_tax(5001.0)
    summary.check("Tax Tier 1 lower bound (5,001 ₪)", abs(t_5001 - 15.00) < 0.05, f"Tax = {t_5001} ₪ (0.3%)")
    t_50k = calculate_wealth_tax(50000.0)
    summary.check("Tax Tier 1 upper bound (50,000 ₪)", abs(t_50k - 150.00) < 0.05, f"Tax = {t_50k} ₪ (0.3%)")

    # Tier 2 (50,001 - 500,000 ₪) -> 1.0%
    t_50001 = calculate_wealth_tax(50001.0)
    summary.check("Tax Tier 2 lower bound (50,001 ₪)", abs(t_50001 - 500.01) < 0.05, f"Tax = {t_50001} ₪ (1.0%)")
    t_500k = calculate_wealth_tax(500000.0)
    summary.check("Tax Tier 2 upper bound (500,000 ₪)", abs(t_500k - 5000.00) < 0.05, f"Tax = {t_500k} ₪ (1.0%)")

    # Tier 3 (500,001 - 5,000,000 ₪) -> 2.5%
    t_500001 = calculate_wealth_tax(500001.0)
    summary.check("Tax Tier 3 lower bound (500,001 ₪)", abs(t_50001 - 500.01) < 0.05, f"Tax = {t_500001} ₪ (2.5%)")
    t_1m = calculate_wealth_tax(1000000.0)
    summary.check("Tax Tier 3 (1,000,000 ₪)", abs(t_1m - 25000.00) < 0.05, f"Tax = {t_1m} ₪ (2.5%)")
    t_5m = calculate_wealth_tax(5000000.0)
    summary.check("Tax Tier 3 upper bound (5,000,000 ₪)", abs(t_5m - 125000.00) < 0.05, f"Tax = {t_5m} ₪ (2.5%)")

    # Tier 4 (> 5,000,000 ₪) -> 5.0%
    t_5000001 = calculate_wealth_tax(5000001.0)
    summary.check("Tax Tier 4 lower bound (5,000,001 ₪)", abs(t_5000001 - 250000.05) < 0.05, f"Tax = {t_5000001} ₪ (5.0%)")
    t_10m = calculate_wealth_tax(10000000.0)
    summary.check("Tax Tier 4 (10,000,000 ₪)", abs(t_10m - 500000.00) < 0.05, f"Tax = {t_10m} ₪ (5.0%)")

    # Idle Surcharge 1.5x Multiplier Rules:
    # 1. wallet <= 500,000 NEVER receives surcharge
    t_500k_idle = calculate_wealth_tax(500000.0, idle_hours=100.0)
    summary.check("Idle Surcharge boundary (500,000 ₪ at 100h idle)", t_500k_idle == 5000.00, f"Tax = {t_500k_idle} (no multiplier)")

    # 2. wallet > 500,000 at 71.99h idle: NO surcharge
    t_mega_almost_idle = calculate_wealth_tax(1000000.0, idle_hours=71.99)
    summary.check("Idle Surcharge boundary (1M at 71.99h idle)", t_mega_almost_idle == 25000.00, f"Tax = {t_mega_almost_idle} (no multiplier)")

    # 3. wallet > 500,000 at 72.00h idle: MUST receive 1.5x surcharge
    t_mega_idle = calculate_wealth_tax(1000000.0, idle_hours=72.00)
    summary.check("Idle Surcharge triggered (1M at 72.00h idle)", t_mega_idle == 37500.00, f"Tax = {t_mega_idle} (2.5% * 1.5 = 3.75%)")

    # 4. 10M wallet at 72h idle: 5.0% * 1.5 = 7.5% -> 750,000 ₪
    t_super_idle = calculate_wealth_tax(10000000.0, idle_hours=72.00)
    summary.check("Idle Surcharge Tier 4 (10M at 72h idle)", t_super_idle == 750000.00, f"Tax = {t_super_idle} (5.0% * 1.5 = 7.5%)")

    # -------------------------------------------------------------------------
    # 2. /raid_oligarch CLASS WARS & SYBIL DEFENSES
    # -------------------------------------------------------------------------
    print("\n--- SECTION 2: /raid_oligarch SYBIL, GEAR & CONFISCATION MATH ---")

    db, db_file = await create_isolated_db()
    try:
        # Sybil test 1: < 5 voters
        res_few = await execute_oligarch_raid(db, [1, 2, 3, 4], 999, "b")
        summary.check("Sybil Defense: <5 voters rejected", res_few["ok"] is False and "Недостаточно" in res_few["error"], res_few["error"])

        # Sybil test 2: duplicates (5 voter IDs, but only 2 unique)
        res_dups = await execute_oligarch_raid(db, [1, 2, 1, 2, 1], 999, "b")
        summary.check("Sybil Defense: duplicate voter IDs rejected", res_dups["ok"] is False and "Недостаточно" in res_dups["error"], res_dups["error"])

        # Setup 5 voters in DB
        voters = [101, 102, 103, 104, 105]
        for v in voters:
            await common.database.add_user_global_balance(db, v, "b", 500.0)
            await db.execute("UPDATE Users SET posts_count = 30 WHERE user_id = ?", (v,))

        target_oli = 901
        await common.database.add_user_global_balance(db, target_oli, "b", 800000.0)

        # Sybil test 3: voter balance >= 5000 (disqualified)
        await common.database.add_user_global_balance(db, voters[4], "b", 4500.0) # now 5000
        res_rich_voter = await execute_oligarch_raid(db, voters, target_oli, "b")
        summary.check("Sybil Defense: voter with balance >= 5000 disqualified", res_rich_voter["ok"] is False, res_rich_voter.get("error"))

        # Restore voter 5 to balance < 5000
        await common.database.deduct_user_global_balance(db, voters[4], "b", 4500.0)

        # Sybil test 4: voter posts < 25 (disqualified)
        await db.execute("UPDATE Users SET posts_count = 24 WHERE user_id = ?", (voters[4],))
        res_few_posts = await execute_oligarch_raid(db, voters, target_oli, "b")
        summary.check("Sybil Defense: voter with posts < 25 disqualified", res_few_posts["ok"] is False, res_few_posts.get("error"))

        # Restore voter 5 posts to 25
        await db.execute("UPDATE Users SET posts_count = 25 WHERE user_id = ?", (voters[4],))

        # Target Defense 1: Diplomatic Passport
        ai_pass = {"diplomatic_passport_until": int(time.time()) + 3600}
        await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ?", (json.dumps(ai_pass), target_oli))
        res_pass = await execute_oligarch_raid(db, voters, target_oli, "b")
        summary.check(
            "Defense: Diplomatic Passport blocks raid",
            res_pass["ok"] is False and res_pass.get("blocked") is True and "Дипломатический Паспорт" in res_pass["error"],
            res_pass.get("error")
        )
        summary.check("Diplomatic Passport: 0 shekels deducted", await common.database.get_user_global_balance(db, target_oli) == 800000.0)

        # Target Defense 2: ОБЭП Extinguisher (2 charges)
        ai_ext = {"extinguisher_obep": True, "extinguisher_obep_charges": 2}
        await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ?", (json.dumps(ai_ext), target_oli))

        res_ext1 = await execute_oligarch_raid(db, voters, target_oli, "b")
        summary.check(
            "Defense: ОБЭП Extinguisher blocks raid (charge 2 -> 1)",
            res_ext1["ok"] is False and res_ext1.get("blocked") is True and "Огнетушитель ОБЭП" in res_ext1["error"],
            res_ext1.get("error")
        )
        async with db.execute("SELECT active_items FROM Users WHERE user_id = ?", (target_oli,)) as c:
            ai_now = json.loads((await c.fetchone())[0])
            summary.check("ОБЭП Extinguisher: exactly 1 charge consumed", ai_now.get("extinguisher_obep_charges") == 1)

        res_ext2 = await execute_oligarch_raid(db, voters, target_oli, "b")
        summary.check(
            "Defense: ОБЭП Extinguisher blocks raid (charge 1 -> 0, removed)",
            res_ext2["ok"] is False and res_ext2.get("blocked") is True,
            res_ext2.get("error")
        )
        async with db.execute("SELECT active_items FROM Users WHERE user_id = ?", (target_oli,)) as c:
            ai_now = json.loads((await c.fetchone())[0])
            summary.check("ОБЭП Extinguisher: item purged after final charge", "extinguisher_obep" not in ai_now)

        # Confiscation Math 1: 10% on 800k -> 80k confiscated, 70% burn (56k), 30% to 5 workers (24k / 5 = 4.8k)
        fund_before = await common.database.get_abu_fund_total(db)
        res_success = await execute_oligarch_raid(db, voters, target_oli, "b")
        summary.check("Raid executes after defenses consumed", res_success["ok"] is True)
        summary.check("Confiscation: 10% of 800,000 = 80,000 ₪", res_success["confiscated"] == 80000.0)
        summary.check("Burn: 70% of 80,000 = 56,000 ₪ to Abu Fund", res_success["burned_to_abu"] == 56000.0)
        summary.check("Redistribution: 30% of 80,000 = 24,000 ₪ total", res_success["distributed_total"] == 24000.0)
        summary.check("Per Voter: 24,000 / 5 = 4,800 ₪ each", res_success["per_voter"] == 4800.0)
        summary.check("Target Balance after: 800k - 80k = 720,000 ₪", await common.database.get_user_global_balance(db, target_oli) == 720000.0)

        # Confiscation Math 2: Cap at 200,000 ₪ on mega-wallet (5,000,000 ₪)
        mega_oli = 902
        await common.database.add_user_global_balance(db, mega_oli, "b", 5000000.0)
        # Reset voters' balances to < 5000
        for v in voters:
            await common.database.deduct_user_global_balance(db, v, "b", 5000.0)

        res_cap = await execute_oligarch_raid(db, voters, mega_oli, "b")
        summary.check("Confiscation Cap: 10% of 5M (500k) capped at 200,000 ₪", res_cap["confiscated"] == 200000.0)
        summary.check("Burn: 70% of 200,000 = 140,000 ₪", res_cap["burned_to_abu"] == 140000.0)
        summary.check("Redistribution: 30% of 200,000 = 60,000 ₪ (12,000 ₪/voter)", res_cap["distributed_total"] == 60000.0 and res_cap["per_voter"] == 12000.0)
        summary.check("Mega-Oligarch Balance: 5M - 200k = 4,800,000 ₪", await common.database.get_user_global_balance(db, mega_oli) == 4800000.0)

    finally:
        await db.close()
        try:
            os.remove(db_file)
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # 3. M2 SHOP NON-BUYABLE RELIC GUARD (cb_shop_buy)
    # -------------------------------------------------------------------------
    print("\n--- SECTION 3: M2 SHOP NON-BUYABLE RELIC GUARD (cb_shop_buy) ---")

    relics = [
        "hat_golden_foil",
        "hat_cyber_ushanka",
        "body_dva_ch_mantle",
        "body_padishah_mantle",
        "face_monocle",
    ]
    expected_err = "Этот предмет является уникальной реликвией из кейсов и не продается в обычном магазине!"

    db, db_file = await create_isolated_db()
    try:
        # Verify catalog definitions
        for r in relics:
            meta = CLOTHING_CATALOG.get(r, {})
            summary.check(f"Catalog Check: {r} has non_buyable=True", meta.get("non_buyable") is True)

        # Test balance=0 and balance=10,000,000 for each relic
        for idx, r in enumerate(relics):
            # Case A: Balance = 0 ₪
            uid_0 = 70000 + idx * 2
            await common.database.add_user_global_balance(db, uid_0, "b", 0.0)

            cb_0 = MagicMock()
            cb_0.from_user.id = uid_0
            cb_0.data = f"shop_buy_{r}"
            cb_0.answer = AsyncMock()

            with patch("main.get_pool", AsyncMock(return_value=db)), \
                 patch("shared_state.record_shop_purchase", MagicMock()):
                await cb_shop_buy(cb_0, "b")

            called_text_0 = cb_0.answer.call_args[0][0] if cb_0.answer.call_args else ""
            called_alert_0 = cb_0.answer.call_args[1].get("show_alert") if cb_0.answer.call_args else None
            bal_0 = await common.database.get_user_global_balance(db, uid_0)

            summary.check(
                f"Shop Guard [{r}] at 0 ₪: exact rejection message",
                called_text_0 == expected_err,
                f"'{called_text_0}'"
            )
            summary.check(
                f"Shop Guard [{r}] at 0 ₪: show_alert=True and 0 ₪ deducted",
                called_alert_0 is True and bal_0 == 0.0,
                f"show_alert={called_alert_0}, balance={bal_0}"
            )

            # Case B: Balance = 10,000,000 ₪
            uid_rich = 70000 + idx * 2 + 1
            await common.database.add_user_global_balance(db, uid_rich, "b", 10000000.0)

            cb_rich = MagicMock()
            cb_rich.from_user.id = uid_rich
            cb_rich.data = f"shop_buy_{r}"
            cb_rich.answer = AsyncMock()

            with patch("main.get_pool", AsyncMock(return_value=db)), \
                 patch("shared_state.record_shop_purchase", MagicMock()):
                await cb_shop_buy(cb_rich, "b")

            called_text_rich = cb_rich.answer.call_args[0][0] if cb_rich.answer.call_args else ""
            called_alert_rich = cb_rich.answer.call_args[1].get("show_alert") if cb_rich.answer.call_args else None
            bal_rich = await common.database.get_user_global_balance(db, uid_rich)

            summary.check(
                f"Shop Guard [{r}] at 10M ₪: exact rejection message",
                called_text_rich == expected_err,
                f"'{called_text_rich}'"
            )
            summary.check(
                f"Shop Guard [{r}] at 10M ₪: show_alert=True and 0 ₪ deducted",
                called_alert_rich is True and bal_rich == 10000000.0,
                f"show_alert={called_alert_rich}, balance={bal_rich}"
            )

    finally:
        await db.close()
        try:
            os.remove(db_file)
        except Exception:
            pass

    print("\n" + "=" * 75)
    print(f"VERIFICATION SUMMARY: {summary.passed} PASSED, {summary.failed} FAILED")
    print("=" * 75)

    return summary.failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_checks())
    sys.exit(0 if success else 1)
