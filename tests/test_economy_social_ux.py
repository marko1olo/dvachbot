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
import pytest

from bank_engine import (
    BANK_TIERS,
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

