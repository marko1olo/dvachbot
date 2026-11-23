# -*- coding: utf-8 -*-
"""
tests/test_economy_social_ux.py — Comprehensive UX & Edge-Case Test Suite
for Bank of Abu, Gig/Work Engine, and P2P Flea Market.

Covers:
1. Input validation and user-friendly error messages (empty, non-numeric, negative, scientific 1e9, NaN, Inf, excessive decimals).
2. Bank time formatting until interest/lockup (human-readable format_remaining_time, no "0ч 0м", day/hour/min/sec breakdowns).
3. Bank early withdrawal warnings, deposit limits, and atomic state updates.
4. Work fatigue recovery time, efficiency badges, and rolling 24h decay.
5. Work vacancy dossiers, gear synergies, gear immunities, and locked vacancy guidance.
6. Market price parsing, listing validation, 5% fee transparency, and empty catalog friendly states.
7. Market transaction safety (own-lot protection, insufficient funds guidance, seller notifications).
"""

import math
import time
from unittest.mock import AsyncMock, patch
import pytest

from bank_engine import (
    BANK_TIERS,
    build_bank_dashboard_view,
    build_bank_hub_kb,
    calculate_deposit_state,
    create_bank_deposit,
    format_remaining_time,
    get_tier_info,
    get_user_bank_summary,
    normalize_tier_id,
    parse_deposit_amount,
    withdraw_bank_deposit,
)
from common.work_engine import (
    WORK_VACANCIES,
    execute_job_action,
    format_all_vacancies_summary,
    format_fatigue_badge,
    format_fatigue_recovery_time,
    format_vacancy_dossier,
    get_user_daily_fatigue_info,
)
from market_engine import (
    buy_market_listing,
    cancel_market_listing,
    create_market_listing,
    get_market_catalog,
    get_market_listing,
    parse_market_price,
)
from common.database import add_user_global_balance, get_user_global_balance


# =============================================================================
# PART 1: BANK INPUT VALIDATION & TIME FORMATTING UX
# =============================================================================

def test_bank_time_formatting_various_durations():
    """Verify format_remaining_time outputs clean, player-friendly Russian strings without '0ч 0м' artifacts."""
    # Sub-minute
    assert format_remaining_time(0) == "0 сек."
    assert format_remaining_time(-15) == "0 сек."
    assert format_remaining_time(1) == "1 сек."
    assert format_remaining_time(45) == "45 сек."
    assert format_remaining_time(59) == "59 сек."

    # Minutes & seconds
    assert format_remaining_time(60) == "1 мин."
    assert format_remaining_time(135) == "2 мин. 15 сек."
    assert format_remaining_time(1800) == "30 мин."
    assert format_remaining_time(3540) == "59 мин."

    # Hours & minutes
    assert format_remaining_time(3600) == "1 ч."
    assert format_remaining_time(8124) == "2 ч. 15 мин."
    assert format_remaining_time(7200) == "2 ч."
    assert format_remaining_time(7500) == "2 ч. 5 мин."

    # Days & hours (e.g. Skuf 72h lockup)
    assert format_remaining_time(86400) == "1 дн."
    assert format_remaining_time(93600) == "1 дн. 2 ч."
    assert format_remaining_time(259200) == "3 дн."
    assert format_remaining_time(266400) == "3 дн. 2 ч."

    # Invalid / edge types
    assert format_remaining_time(float("nan")) == "0 сек."
    assert format_remaining_time(float("inf")) == "0 сек."


def test_bank_deposit_amount_parsing_edge_cases():
    """Test parse_deposit_amount handles all human inputs, slangs, keywords, and rejects malformed/poisoned inputs."""
    wallet = 100_000.0

    # Normal numbers
    assert parse_deposit_amount("500", wallet) == 500.0
    assert parse_deposit_amount("150.50", wallet) == 150.50
    assert parse_deposit_amount("150,50", wallet) == 150.50
    assert parse_deposit_amount("50 000", wallet) == 50000.0

    # Slang & Currency suffixes
    assert parse_deposit_amount("50k", wallet) == 50000.0
    assert parse_deposit_amount("50к", wallet) == 50000.0
    assert parse_deposit_amount("1.5m", wallet) == 1500000.0
    assert parse_deposit_amount("1.5м", wallet) == 1500000.0
    assert parse_deposit_amount("2кк", wallet) == 2000000.0
    assert parse_deposit_amount("500 ₪", wallet) == 500.0
    assert parse_deposit_amount("1000 руб", wallet) == 1000.0
    assert parse_deposit_amount("250 шекелей", wallet) == 250.0

    # Keywords
    assert parse_deposit_amount("all", wallet) == 100000.0
    assert parse_deposit_amount("все", wallet) == 100000.0
    assert parse_deposit_amount("half", wallet) == 50000.0
    assert parse_deposit_amount("пол", wallet) == 50000.0
    assert parse_deposit_amount("треть", wallet) == 33333.33
    assert parse_deposit_amount("четверть", wallet) == 25000.0

    # Percentages
    assert parse_deposit_amount("50%", wallet) == 50000.0
    assert parse_deposit_amount("100%", wallet) == 100000.0
    assert parse_deposit_amount("25%", wallet) == 25000.0

    # Reject Malformed / Poisoned / Tech inputs
    assert parse_deposit_amount("", wallet) is None
    assert parse_deposit_amount("   ", wallet) is None
    assert parse_deposit_amount("abc", wallet) is None
    assert parse_deposit_amount("!@#$%", wallet) is None
    assert parse_deposit_amount("nan", wallet) is None
    assert parse_deposit_amount("+nan", wallet) is None
    assert parse_deposit_amount("-nan", wallet) is None
    assert parse_deposit_amount("inf", wallet) is None
    assert parse_deposit_amount("-inf", wallet) is None
    assert parse_deposit_amount("infinity", wallet) is None
    assert parse_deposit_amount("-500", wallet) is None
    assert parse_deposit_amount("0", wallet) is None
    assert parse_deposit_amount("1e25", wallet) is None
    assert parse_deposit_amount("200%", wallet) is None


@pytest.mark.asyncio
async def test_bank_deposit_creation_ux_validation(isolated_test_db):
    """Test create_bank_deposit provides friendly error messages on all invalid parameters."""
    db = isolated_test_db
    user_id = 10001
    await add_user_global_balance(db, user_id, "b", 5000.0)

    # 1. Negative amount
    ok, dep, err = await create_bank_deposit(db, user_id, "b", "sych", -100)
    assert not ok
    assert "положительным числом больше 0" in err

    # 2. Zero amount
    ok, dep, err = await create_bank_deposit(db, user_id, "b", "sych", 0)
    assert not ok
    assert "положительным числом больше 0" in err

    # 3. NaN / Inf
    ok, dep, err = await create_bank_deposit(db, user_id, "b", "sych", float("nan"))
    assert not ok
    assert "положительным числом больше 0" in err

    ok, dep, err = await create_bank_deposit(db, user_id, "b", "sych", float("inf"))
    assert not ok
    assert "положительным числом больше 0" in err

    # 4. Exorbitant amount
    ok, dep, err = await create_bank_deposit(db, user_id, "b", "sych", 2_000_000_000)
    assert not ok
    assert "Максимальная сумма разового вклада" in err

    # 5. Amount below minimum for tier (Skuf min is 50 ₪)
    ok, dep, err = await create_bank_deposit(db, user_id, "b", "skuf", 20)
    assert not ok
    assert "Минимальная сумма для тарифа" in err
    assert "50" in err

    # 6. Insufficient funds
    ok, dep, err = await create_bank_deposit(db, user_id, "b", "sych", 10000)
    assert not ok
    assert "Недостаточно шекелей в кошельке" in err
    assert "5,000" in err

    # 7. Valid deposit succeeds and sets remaining_lock_text
    ok, dep, err = await create_bank_deposit(db, user_id, "b", "skuf", 500)
    assert ok
    assert dep["principal"] == 500.0
    assert dep["is_locked"] is True
    assert dep["remaining_lock_sec"] > 0


@pytest.mark.asyncio
async def test_bank_early_withdrawal_warning_ux(isolated_test_db):
    """Test withdraw_bank_deposit provides clear Russian warning on early withdrawal with penalties and remaining lock time."""
    db = isolated_test_db
    user_id = 10002
    await add_user_global_balance(db, user_id, "b", 1000.0)

    # Open 72h Skuf deposit
    ok, dep, _ = await create_bank_deposit(db, user_id, "b", "skuf", 500.0)
    assert ok
    dep_id = dep["id"]

    # Attempt standard withdrawal while locked
    ok, payout, principal, interest, fee, is_def, err = await withdraw_bank_deposit(
        db, dep_id, user_id, "b", force_early=False
    )
    assert not ok
    # Must contain human readable remaining time, penalty details, and interest burn notice
    assert "заблокирован" in err
    assert "При досрочном снятии" in err
    assert "штраф 3%" in err
    assert "0ч 0м" not in err

    # Now force early withdrawal
    ok, payout, principal, interest, fee, is_def, err = await withdraw_bank_deposit(
        db, dep_id, user_id, "b", force_early=True
    )
    assert ok
    assert fee == 15.0  # 3% of 500
    assert payout == 485.0
    assert interest == 0.0

    # Ensure deposit cannot be withdrawn twice
    ok2, _, _, _, _, _, err2 = await withdraw_bank_deposit(db, dep_id, user_id, "b", force_early=True)
    assert not ok2
    assert "уже закрыт" in err2


# =============================================================================
# PART 2: WORK ENGINE FATIGUE, DOSSIERS & REQUIREMENTS UX
# =============================================================================

def test_work_fatigue_recovery_time_calculation():
    """Verify get_user_daily_fatigue_info calculates exact time until oldest shift decays from 24h rolling window."""
    now = time.time()

    # Case 1: Fresh worker (no shifts)
    info0 = get_user_daily_fatigue_info({}, now=now)
    assert info0["shifts_today"] == 0
    assert info0["efficiency_pct"] == 100
    assert info0["recovery_sec"] == 0
    assert info0["recovery_text"] == ""

    # Case 2: 4 shifts (Tier 2: 80% efficiency, oldest shift occurred 2 hours ago = now - 7200)
    recent_shifts = {
        "bottles": [now - 7200, now - 5400, now - 3600, now - 1800]
    }
    info1 = get_user_daily_fatigue_info(recent_shifts, now=now)
    assert info1["shifts_today"] == 4
    assert info1["efficiency_pct"] == 80
    # Oldest shift was 2h ago, so it will expire in 22h (86400 - 7200 = 79200s)
    assert info1["recovery_sec"] == 79200
    assert "22 ч." in info1["recovery_text"]

    # Verify badge formatting
    badge = format_fatigue_badge(info1)
    assert "Эффективность: 80%" in badge
    assert "усталость -20%" in badge
    assert "спад через 22 ч." in badge


def test_work_vacancy_dossier_formatting():
    """Verify format_vacancy_dossier renders rich player-facing breakdown with salary, cooldown, risks, and gear synergies."""
    # 1. Entry level job
    dossier_bottles = format_vacancy_dossier("bottles", user_shifts=0, current_items={})
    assert "Сбор стеклотары" in dossier_bottles
    assert "Уровень 1 • Бомж" in dossier_bottles
    assert "Доступно для работы" in dossier_bottles
    assert "Зарплата:" in dossier_bottles
    assert "Кулдаун:</b> 3 мин." in dossier_bottles
    assert "Риск провала:</b> 0% (без риска)" in dossier_bottles
    assert "Мусорный Лутбокс" in dossier_bottles

    # 2. High-tier locked job
    dossier_scam = format_vacancy_dossier("scam", user_shifts=5, current_items={})
    assert "Теневой Арбитраж & Скам" in dossier_scam
    assert "Заблокировано" in dossier_scam
    assert "требуется 85 смен" in dossier_scam
    assert "осталось 80" in dossier_scam
    assert "Риск провала:</b> 22%" in dossier_scam
    assert "Зеркальный Щит" in dossier_scam

    # 3. Gear synergy effects reflected in dossier
    gear_items = {
        "equipped_torso": "body_wasserman",  # +25% salary
        "equipped_feet": "feet_slippers",     # -20% cooldown
        "equipped_head": "hat_helmet",        # Fine immunity
    }
    dossier_buffed = format_vacancy_dossier("scam", user_shifts=100, current_items=gear_items)
    assert "скидка 20% от тапок" in dossier_buffed
    assert "иммунитет от 🪖 Шлема ОМОНа" in dossier_buffed
    assert "Жилетка (+25%)" in dossier_buffed

    # 4. Non-existent job
    assert format_vacancy_dossier("unknown_job") == "❌ Вакансия не найдена."


def test_work_all_vacancies_summary():
    """Verify format_all_vacancies_summary outputs all career tiers with status icons."""
    summary = format_all_vacancies_summary(user_shifts=5)
    assert "СПИСОК ВСЕХ ПРОФЕССИЙ" in summary
    assert "✅" in summary  # Level 1-2 unlocked
    assert "🔒" in summary  # Level 3+ locked


def test_work_execution_locked_and_cooldown_error_ux():
    """Verify execute_job_action returns clear, helpful Russian instructions when locked or cooling down."""
    now = int(time.time())

    # 1. Locked vacancy
    items = {"work_shifts": 2, "work_cooldowns": {}, "recent_shifts": {}}
    res = execute_job_action("deputy", items)  # requires 120 shifts
    assert not res.is_success
    assert "Вакансия заблокирована!" in res.text_message
    assert "Требуется стаж: 120 смен" in res.text_message
    assert "у тебя: 2" in res.text_message
    assert "осталось: 118" in res.text_message

    # 2. Cooldown active
    items_cd = {
        "work_shifts": 0,
        "work_cooldowns": {"bottles": now - 30},  # 30s ago, cooldown is 180s -> 150s left
        "recent_shifts": {}
    }
    res_cd = execute_job_action("bottles", items_cd)
    assert not res_cd.is_success
    assert "Кулдаун!" in res_cd.text_message
    assert "Эта смена будет доступна через 2 мин" in res_cd.text_message


# =============================================================================
# PART 3: MARKET PRICE PARSING, FEES & EMPTY STATES UX
# =============================================================================

def test_market_price_parsing():
    """Verify parse_market_price correctly parses valid prices and safely rejects poisons, NaNs, and negatives."""
    # Valid formats
    assert parse_market_price(500) == 500.0
    assert parse_market_price("500") == 500.0
    assert parse_market_price("500.25") == 500.25
    assert parse_market_price("500,75") == 500.75
    assert parse_market_price("50k") == 50000.0
    assert parse_market_price("50к") == 50000.0
    assert parse_market_price("1.5m") == 1500000.0
    assert parse_market_price("1.5м") == 1500000.0
    assert parse_market_price("50 000") == 50000.0
    assert parse_market_price("500 ₪") == 500.0
    assert parse_market_price("1000 руб") == 1000.0

    # Minimum boundary
    assert parse_market_price(1.0) == 1.0
    assert parse_market_price("1") == 1.0
    assert parse_market_price(0.99) is None

    # Maximum boundary
    assert parse_market_price(100_000_000) == 100000000.0
    assert parse_market_price(100_000_001) is None

    # Invalid / Disallowed
    assert parse_market_price(None) is None
    assert parse_market_price("") is None
    assert parse_market_price("abc") is None
    assert parse_market_price("nan") is None
    assert parse_market_price("+nan") is None
    assert parse_market_price("-nan") is None
    assert parse_market_price("inf") is None
    assert parse_market_price("-inf") is None
    assert parse_market_price("-500") is None
    assert parse_market_price("0") is None
    assert parse_market_price(float("nan")) is None
    assert parse_market_price(float("inf")) is None


@pytest.mark.asyncio
async def test_market_empty_catalog_ux(isolated_test_db):
    """Verify get_market_catalog on an empty database returns empty results cleanly with total_count=0."""
    db = isolated_test_db
    items, total_pages, total_count = await get_market_catalog(db, category="all")
    assert items == []
    assert total_pages == 1
    assert total_count == 0


@pytest.mark.asyncio
async def test_market_listing_and_buyer_protection_ux(isolated_test_db):
    """Verify market listing creation, fee calculation, own-lot blocking, and insufficient balance messages."""
    db = isolated_test_db
    seller_id = 20001
    buyer_id = 20002

    # Give seller a weapon in active_items
    from market_engine import _save_user_active_items
    await _save_user_active_items(db, seller_id, "b", {"knife_gun": True})

    # 1. Invalid price rejection
    ok, _, err = await create_market_listing(db, seller_id, "b", "knife", -50)
    assert not ok
    assert "Некорректная цена" in err or "не менее 1.00 ₪" in err

    ok, _, err = await create_market_listing(db, seller_id, "b", "knife", float("nan"))
    assert not ok
    assert "Некорректная цена" in err

    # 2. Valid listing creation (escrows knife)
    ok, listing, err = await create_market_listing(db, seller_id, "b", "knife", 200.0)
    assert ok
    lot_id = listing["id"]
    assert listing["price"] == 200.0

    # Ensure knife is removed from seller active items
    from market_engine import _load_user_active_items_for_update
    seller_items = await _load_user_active_items_for_update(db, seller_id, "b")
    assert not seller_items.get("knife_gun")

    # 3. Seller cannot buy their own lot
    ok, _, _, _, _, _, buy_err = await buy_market_listing(db, lot_id, seller_id, "b")
    assert not ok
    assert "Нельзя покупать свой собственный лот" in buy_err

    # 4. Buyer with insufficient balance gets friendly message
    await add_user_global_balance(db, buyer_id, "b", 50.0)
    ok, _, _, _, _, _, buy_err2 = await buy_market_listing(db, lot_id, buyer_id, "b")
    assert not ok
    assert "Недостаточно шекелей в кошельке" in buy_err2
    assert "50.00 ₪" in buy_err2
    assert "200.00 ₪" in buy_err2

    # 5. Buyer with sufficient balance buys successfully
    await add_user_global_balance(db, buyer_id, "b", 500.0)  # total 550.0
    ok, s_id, price, payout, fee, item_dict, _ = await buy_market_listing(db, lot_id, buyer_id, "b")
    assert ok
    assert s_id == seller_id
    assert price == 200.0
    assert fee == 10.0  # 5% of 200
    assert payout == 190.0

    # Ensure item transferred to buyer
    buyer_items = await _load_user_active_items_for_update(db, buyer_id, "b")
    assert buyer_items.get("knife_gun") is True

    # Ensure seller received payout
    seller_bal = await get_user_global_balance(db, seller_id)
    assert seller_bal == 190.0


@pytest.mark.asyncio
async def test_market_cancel_listing_ux(isolated_test_db):
    """Verify cancelling listing restores item and prevents cancelling someone else's lot."""
    db = isolated_test_db
    seller_id = 30001
    stranger_id = 30002

    from market_engine import _save_user_active_items, _load_user_active_items_for_update
    await _save_user_active_items(db, seller_id, "b", {"pepperspray_gun": True})

    ok, listing, _ = await create_market_listing(db, seller_id, "b", "pepperspray", 150.0)
    assert ok
    lot_id = listing["id"]

    # Stranger cannot cancel seller's lot
    ok, _, err = await cancel_market_listing(db, lot_id, stranger_id, "b")
    assert not ok
    assert "не являетесь владельцем" in err

    # Owner cancels successfully
    ok, item_dict, _ = await cancel_market_listing(db, lot_id, seller_id, "b")
    assert ok
    assert item_dict["item_id"] == "pepperspray"

    # Item restored to seller
    seller_items = await _load_user_active_items_for_update(db, seller_id, "b")
    assert seller_items.get("pepperspray_gun") is True

    # Double cancel blocked
    ok2, _, err2 = await cancel_market_listing(db, lot_id, seller_id, "b")
    assert not ok2
    assert "уже не активен" in err2


# =============================================================================
# PART 4: COMPREHENSIVE BANK CHAT PARSING & WORK PENALTY UX TESTS
# =============================================================================

def test_bank_chat_deposit_parsing_and_action_words():
    """Verify chat message deposit parsing supports action words, slangs, comma thousands, and tiers."""
    from bank_engine import parse_amount_and_tier, parse_deposit_amount

    # Action words prefixing or suffixing amounts
    res1 = parse_amount_and_tier("вклад 1000")
    assert res1 is not None
    amt_str1, tier1 = res1
    assert parse_deposit_amount(amt_str1, 5000.0) == 1000.0
    assert tier1 == "sych"

    res2 = parse_amount_and_tier("деп 50к")
    assert res2 is not None
    amt_str2, tier2 = res2
    assert parse_deposit_amount(amt_str2, 100_000.0) == 50000.0
    assert tier2 == "sych"

    res3 = parse_amount_and_tier("положить все")
    assert res3 is not None
    amt_str3, tier3 = res3
    assert parse_deposit_amount(amt_str3, 25000.0) == 25000.0
    assert tier3 == "sych"

    res4 = parse_amount_and_tier("закинуть 5000 в скуф")
    assert res4 is not None
    amt_str4, tier4 = res4
    assert parse_deposit_amount(amt_str4, 10000.0) == 5000.0
    assert tier4 == "skuf"

    res5 = parse_amount_and_tier("депозит 100к в ммм")
    assert res5 is not None
    amt_str5, tier5 = res5
    assert parse_deposit_amount(amt_str5, 200_000.0) == 100000.0
    assert tier5 == "mmm_abu"

    res6 = parse_amount_and_tier("в банк 1000")
    assert res6 is not None
    amt_str6, tier6 = res6
    assert parse_deposit_amount(amt_str6, 5000.0) == 1000.0

    # Thousands with comma ("100,000" -> 100000) vs decimal with comma ("150,50" -> 150.50)
    assert parse_deposit_amount("100,000", 500_000.0) == 100000.0
    assert parse_deposit_amount("1,000,000", 2_000_000.0) == 1000000.0
    assert parse_deposit_amount("150,50", 1000.0) == 150.50

    # Numbers with leading '+'
    assert parse_deposit_amount("+100", 1000.0) == 100.0
    assert parse_deposit_amount("+50к", 100_000.0) == 50000.0

    # Rejection of ordinary chat messages or poisoned input
    assert parse_amount_and_tier("привет как дела на борде") is None
    assert parse_amount_and_tier("лол кек чебурек") is None
    assert parse_amount_and_tier("-500") is None
    assert parse_amount_and_tier("nan") is None
    assert parse_amount_and_tier("inf") is None
    assert parse_amount_and_tier("/deposit 1000") is None  # Commands are skipped by filter


@pytest.mark.asyncio
async def test_bank_zero_balance_deposit_ux(isolated_test_db):
    """Verify friendly handling when user attempts to deposit with 0 balance or invalid amount."""
    db = isolated_test_db
    user_id = 40001

    # User has 0 balance
    bal = await get_user_global_balance(db, user_id)
    assert bal == 0.0

    # parse_deposit_amount with 'все' returns 0.0 on 0 wallet
    assert parse_deposit_amount("все", bal) == 0.0

    # create_bank_deposit fails cleanly with explanatory message
    ok, dep, err = await create_bank_deposit(db, user_id, "b", "sych", 0.0)
    assert not ok
    assert dep is None
    assert "положительным числом больше 0" in err

    # User attempts to deposit 100 ₪ but has 0 ₪ in wallet
    ok2, dep2, err2 = await create_bank_deposit(db, user_id, "b", "sych", 100.0)
    assert not ok2
    assert dep2 is None
    assert "Недостаточно шекелей в кошельке" in err2
    assert "баланс: 0 ₪" in err2


@pytest.mark.asyncio
async def test_work_cooldown_and_zero_balance_penalty_ux(isolated_test_db):
    """Verify job cooldown timers and soft overdraft protection on penalties."""
    db = isolated_test_db
    user_id = 50001
    now = int(time.time())

    items = {
        "work_shifts": 10,
        "work_cooldowns": {"bottles": now - 30},  # Ran 30s ago, 150s remaining of 180s cd
        "recent_shifts": {}
    }

    # Shift is on cooldown -> returns friendly timer message
    res = execute_job_action("bottles", items, user_id=user_id)
    is_success, amt, msg, dropped = res
    assert not is_success
    assert amt == 0
    assert "⏳ Кулдаун!" in msg
    assert "мин" in msg or "сек" in msg

    # Soft overdraft simulation: user balance is 0, penalty is incurred
    user_bal = await get_user_global_balance(db, user_id)
    assert user_bal == 0.0

    # Deducting penalty with soft overdraft:
    from common.database import deduct_user_global_balance
    ok, rem_bal = await deduct_user_global_balance(db, user_id, "b", 50.0)
    assert not ok
    assert rem_bal == 0.0
    # Balance remains strictly >= 0 (no negative balance trap)
    final_bal = await get_user_global_balance(db, user_id)
    assert final_bal == 0.0


@pytest.mark.asyncio
async def test_bank_continuous_accrual_and_early_break_penalty(isolated_test_db):
    """Verify continuous interest accrual per second and early withdrawal penalty calculation."""
    db = isolated_test_db
    user_id = 60001
    now = time.time()

    await add_user_global_balance(db, user_id, "b", 1000.0)

    # Open Skuf 3-day term deposit (min 50 ₪)
    ok, dep, err = await create_bank_deposit(db, user_id, "b", "skuf", 500.0)
    assert ok
    dep_id = dep["id"]

    # Check interest accrued after 1 day (86400s)
    state = calculate_deposit_state(dep, current_ts=now + 86400)
    assert state["is_locked"] is True
    # 2.5% daily rate on 500 principal = 12.5 ₪
    assert round(state["accrued_interest"], 1) == 12.5
    assert round(state["total_value"], 1) == 512.5

    # Attempt standard withdrawal while locked -> rejected with remaining time warning
    ok_w, payout, principal, interest, fee, is_def, err_w = await withdraw_bank_deposit(
        db, dep_id, user_id, "b", force_early=False
    )
    assert not ok_w
    assert "заблокирован" in err_w
    assert "При досрочном снятии" in err_w
    assert "штраф 3%" in err_w

    # Execute early withdrawal with force_early=True -> penalty applied, interest lost
    ok_early, p_out, p_princ, p_int, p_fee, p_def, p_err = await withdraw_bank_deposit(
        db, dep_id, user_id, "b", force_early=True
    )
    assert ok_early
    assert p_int == 0.0  # All interest burnt
    assert p_fee == 15.0  # 3% of 500 = 15.0 ₪ penalty
    assert p_out == 485.0  # 500 - 15 = 485 ₪ payout
    assert not p_def

    # Ensure payout credited to wallet
    wallet_after = await get_user_global_balance(db, user_id)
    # Started with 1000, deposited 500 (balance was 500), received 485 payout = 985
    assert wallet_after == 985.0


def test_bank_dashboard_zero_balance_guidance_and_work_hub_button():
    """Verify bank dashboard guides bankrupt users to /work and includes work_hub button in keyboard."""
    # Broke user view
    text_broke, kb_broke = build_bank_dashboard_view(
        wallet_balance=0.0,
        total_principal=0.0,
        total_accrued=0.0,
        deposits=[],
        dirty_balance=0.0
    )
    assert "Твой кошелек и сейф пусты. Заработай шекели на Бирже труда (/work)!" in text_broke

    # All buttons in the bank hub keyboard
    all_callbacks = [
        btn.callback_data
        for row in kb_broke.inline_keyboard
        for btn in row
    ]
    assert "work_hub" in all_callbacks
    assert "bank_refresh" in all_callbacks

    # Non-broke user view
    text_funded, _ = build_bank_dashboard_view(
        wallet_balance=5000.0,
        total_principal=0.0,
        total_accrued=0.0,
        deposits=[],
        dirty_balance=0.0
    )
    assert "У тебя нет активных вкладов. Шекели в кошельке не приносят доход" in text_funded


def test_work_energy_and_health_depleted_guards():
    """Verify execute_job_action rejects shifts with informative advice when energy or health is <= 0."""
    # 0 Energy
    res_e0 = execute_job_action("bottles", {"energy": 0})
    assert res_e0[0] is False
    assert "закончилась энергия (0⚡)" in res_e0[2]
    assert "Flash Ultra" in res_e0[2]

    # Negative Energy
    res_en = execute_job_action("bottles", {"energy": -10})
    assert res_en[0] is False
    assert "закончилась энергия" in res_en[2]

    # 0 Health
    res_h0 = execute_job_action("bottles", {"health": 0})
    assert res_h0[0] is False
    assert "здоровье на нуле (0 HP)" in res_h0[2]
    assert "/cure" in res_h0[2]

    # Negative Health
    res_hn = execute_job_action("bottles", {"health": -5})
    assert res_hn[0] is False
    assert "здоровье на нуле" in res_hn[2]


@pytest.mark.asyncio
async def test_side_hustles_callback_with_none_board_id(isolated_test_db):
    """Verify cb_work_action handles board_id=None without dropping or silently returning."""
    from economy_extension import cb_work_action
    db = isolated_test_db
    user_id = 70001
    await add_user_global_balance(db, user_id, "b", 500.0)

    mock_cb = AsyncMock()
    mock_cb.from_user.id = user_id
    mock_cb.data = "work_bottles"
    mock_cb.answer = AsyncMock()
    mock_cb.message.photo = None
    mock_cb.message.edit_text = AsyncMock()

    with patch("economy_extension.get_pool", return_value=db), \
         patch("main._build_work_card", return_value=("mock_card", None)):
        await cb_work_action(mock_cb, board_id=None)

    # Callback answered and processed (did not abort on if not board_id)
    assert mock_cb.answer.called


@pytest.mark.asyncio
async def test_market_cas_double_buy_prevention(isolated_test_db):
    """Verify atomic CAS in buy_market_listing prevents double spending and concurrent race buys."""
    db = isolated_test_db
    seller_id = 80001
    buyer1_id = 80002
    buyer2_id = 80003

    # Setup seller inventory with an item
    from market_engine import _save_user_active_items
    await _save_user_active_items(db, seller_id, "b", {"knife_gun": True})

    # Setup buyers with balance
    await add_user_global_balance(db, buyer1_id, "b", 500.0)
    await add_user_global_balance(db, buyer2_id, "b", 500.0)

    # Create listing
    ok_list, lot_dict, err_list = await create_market_listing(
        db, seller_id, "b", "knife", 200.0
    )
    assert ok_list
    lot_id = lot_dict["id"]

    # First buyer buys lot
    ok1, s1, p1, pay1, fee1, item1, err1 = await buy_market_listing(db, lot_id, buyer1_id, "b")
    assert ok1 is True
    assert p1 == 200.0

    bal_buyer1 = await get_user_global_balance(db, buyer1_id)
    assert bal_buyer1 == 300.0

    # Second buyer attempts to buy the same lot
    ok2, s2, p2, pay2, fee2, item2, err2 = await buy_market_listing(db, lot_id, buyer2_id, "b")
    assert ok2 is False
    assert "уже продан или снят с продажи" in err2

    # Second buyer's balance must remain completely untouched
    bal_buyer2 = await get_user_global_balance(db, buyer2_id)
    assert bal_buyer2 == 500.0


# =============================================================================
# PART 8: IDENTITY MASKING & VICTIM PM DISPATCH IN COMBAT & AUCTION/MARKET
# =============================================================================

from common.anon_identity import get_anon_id, generate_anon_name


def test_anon_identity_masking_combat_and_market():
    """Verify player IDs are masked with hash/names and never leak raw numeric IDs."""
    test_uid = 99887766
    anon_id = get_anon_id(test_uid)
    anon_name = generate_anon_name(test_uid)

    assert isinstance(anon_id, str) and len(anon_id) > 0
    assert isinstance(anon_name, str) and len(anon_name) > 0
    # Must not contain raw numeric string
    assert str(test_uid) not in anon_id
    assert str(test_uid) not in anon_name
    assert "Анон" in anon_name


@pytest.mark.asyncio
async def test_partyvan_victim_pm_and_backfire_masking():
    """Verify cmd_partyvan sends PM to victim with masked attacker name, and backfire masks caller ID."""
    from tests.economy_live import live_economy, live_handler
    from unittest.mock import patch
    import combat_moderation_engine as cme
    import shared_state

    snitch_id = 9101
    victim_id = 9102

    async with live_economy() as live:
        cme.reset_combat_moderation_state()
        shared_state.reset_combat_state()
        await live.seed_user(snitch_id, 1000.0, {"partyvan_gun": True}, posts_count=100)
        await live.seed_user(victim_id, 1000.0, {}, posts_count=100)
        live.aim_at(victim_id)
        msg = live.message(snitch_id)

        # 1. Normal successful arrest
        with patch("combat_moderation_engine.calculate_combat_duration_and_backfire", return_value=(3600, False, 0.1)):
            await live_handler("partyvan")(msg, "b")

            # Check that msg.bot.send_message was called to notify victim_id in PM
            pm_calls = [
                c for c in msg.bot.send_message.call_args_list
                if (c.args and c.args[0] == victim_id) or (c.kwargs.get("chat_id") == victim_id)
            ]
            assert len(pm_calls) >= 1
            pm_text = pm_calls[0].args[1] if len(pm_calls[0].args) > 1 else pm_calls[0].kwargs.get("text", "")
            assert "НА ТЕБЯ ВЫЗВАЛИ ПАТИВЭН В /b/!" in pm_text
            assert generate_anon_name(snitch_id) in pm_text
            assert str(snitch_id) not in pm_text

        # 2. Backfire case (caller arrested by their own false alarm)
        cme.reset_combat_moderation_state()
        shared_state.reset_combat_state()
        snitch_bf = 9103
        victim_bf = 9104
        await live.seed_user(snitch_bf, 1000.0, {"partyvan_gun": True}, posts_count=100)
        await live.seed_user(victim_bf, 1000.0, {}, posts_count=100)
        live.aim_at(victim_bf)
        msg_bf = live.message(snitch_bf)

        with patch("combat_moderation_engine.calculate_combat_duration_and_backfire", return_value=(7200, True, 0.5)):
            await live_handler("partyvan")(msg_bf, "b")

            # Check chat message sent for backfire
            chat_calls = [
                c for c in msg_bf.bot.send_message.call_args_list
                if "ОБЛАВА ПО ЛОЖНОМУ ДОНОСУ!" in (c.args[1] if len(c.args) > 1 else c.kwargs.get("text", ""))
            ]
            assert len(chat_calls) >= 1
            bf_text = chat_calls[0].args[1] if len(chat_calls[0].args) > 1 else chat_calls[0].kwargs.get("text", "")
            # Must NOT contain [ID:9103]
            assert f"[ID:{snitch_bf}]" not in bf_text
            assert str(snitch_bf) not in bf_text
            assert generate_anon_name(snitch_bf) in bf_text


@pytest.mark.asyncio
async def test_curse_and_shoot_victim_pm_notifications():
    """Verify /curse and /shoot send PM notifications with masked attacker identities."""
    from tests.economy_live import live_economy, live_handler
    from unittest.mock import patch
    import combat_moderation_engine as cme
    import shared_state

    attacker_id = 9201
    victim_id = 9202

    async with live_economy() as live:
        cme.reset_combat_moderation_state()
        shared_state.reset_combat_state()
        await live.seed_user(attacker_id, 1000.0, {"laxative_gun": True, "mute_gun": True}, posts_count=100)
        await live.seed_user(victim_id, 1000.0, {}, posts_count=100)

        # 1. Curse
        live.aim_at(victim_id)
        msg_curse = live.message(attacker_id)
        with patch("combat_moderation_engine.calculate_combat_duration_and_backfire", return_value=(3600, False, 0.05)):
            await live_handler("curse")(msg_curse, "b")

            curse_pm_calls = [
                c for c in msg_curse.bot.send_message.call_args_list
                if (c.args and c.args[0] == victim_id) or (c.kwargs.get("chat_id") == victim_id)
            ]
            assert len(curse_pm_calls) >= 1
            c_text = curse_pm_calls[0].args[1] if len(curse_pm_calls[0].args) > 1 else curse_pm_calls[0].kwargs.get("text", "")
            assert "ТЕБЕ ПОДСЫПАЛИ СЛАБИТЕЛЬНОЕ" in c_text
            assert generate_anon_name(attacker_id) in c_text
            assert str(attacker_id) not in c_text

        # 2. Shoot (mutegun)
        cme.reset_combat_moderation_state()
        shared_state.reset_combat_state()
        victim_shoot_id = 9203
        await live.seed_user(victim_shoot_id, 1000.0, {}, posts_count=100)

        live.aim_at(victim_shoot_id)
        msg_shoot = live.message(attacker_id)
        with patch("combat_moderation_engine.calculate_combat_duration_and_backfire", return_value=(1800, False, 0.05)):
            await live_handler("shoot")(msg_shoot, "b")

            shoot_pm_calls = [
                c for c in msg_shoot.bot.send_message.call_args_list
                if (c.args and c.args[0] == victim_shoot_id) or (c.kwargs.get("chat_id") == victim_shoot_id)
            ]
            assert len(shoot_pm_calls) >= 1
            s_text = shoot_pm_calls[0].args[1] if len(shoot_pm_calls[0].args) > 1 else shoot_pm_calls[0].kwargs.get("text", "")
            assert "В тебя выстрелил" in s_text
            assert generate_anon_name(attacker_id) in s_text
            assert str(attacker_id) not in s_text


@pytest.mark.asyncio
async def test_rob_victim_pm_and_ledger_masking():
    """Verify /rob notifies victim in PM with masked robber identity and UserTransactions ledger is masked."""
    from tests.economy_live import live_economy, live_handler
    from unittest.mock import patch
    import combat_moderation_engine as cme
    import shared_state

    robber_id = 9301
    victim_id = 9302

    async with live_economy() as live:
        cme.reset_combat_moderation_state()
        shared_state.reset_combat_state()
        await live.seed_user(robber_id, 1000.0, {"knife_gun": True}, posts_count=100)
        await live.seed_user(victim_id, 2000.0, {}, posts_count=100)
        live.aim_at(victim_id)
        msg_rob = live.message(robber_id)

        # Force successful robbery (roll < 0.6)
        with patch("random.random", return_value=0.1):
            await live_handler("rob")(msg_rob, "b")

            # Verify PM sent to victim
            rob_pm_calls = [
                c for c in msg_rob.bot.send_message.call_args_list
                if (c.args and c.args[0] == victim_id) or (c.kwargs.get("chat_id") == victim_id)
            ]
            assert len(rob_pm_calls) >= 1
            r_text = rob_pm_calls[0].args[1] if len(rob_pm_calls[0].args) > 1 else rob_pm_calls[0].kwargs.get("text", "")
            assert "ТЕБЯ ОГРАБИЛ" in r_text
            assert generate_anon_name(robber_id) in r_text
            assert str(robber_id) not in r_text

            # Check ledger description in UserTransactions
            async with live.db.execute("SELECT description FROM UserTransactions WHERE user_id = ?", (victim_id,)) as cur:
                rows = await cur.fetchall()
                assert len(rows) > 0
                for row in rows:
                    desc = row[0]
                    # Ledger must NOT leak raw robber ID
                    assert str(robber_id) not in desc
                    assert generate_anon_name(robber_id) in desc



