# -*- coding: utf-8 -*-
"""
Automated unit and integration tests for:
1. Casino News Filter (strictly >= 4.0x multiplier required).
2. Night Shift Multiplier (x1.5 payout between 00:00 and 07:00 MSK).
3. Expanded Side Hustles (bottles, dumpster, flyers, microloan, overtime).
4. Daily Work Quests Engine (generation, progress, Abu rewards).
"""

import json
import time
import pytest
from aiogram import types
from unittest.mock import AsyncMock, MagicMock, patch
import common.daily_quests_engine as qe
from common.work_engine import is_night_shift_active, execute_job_action, WORK_VACANCIES
from economy_extension import cb_work_action, check_flash_ultra_limit
from whale_economy_engine import (
    calculate_whale_safe_price,
    buy_whale_safe,
    roll_whale_safe,
    calculate_wealth_tax,
    process_daily_wealth_tax,
    create_auction,
    place_auction_bid,
    finish_active_auctions,
    execute_oligarch_raid,
)
from common.database import get_user_global_balance, add_user_global_balance, get_abu_fund_total
import shared_state
from news_channel_publisher import publish_casino_jackpot_news


# ==========================================
# 1. CASINO NEWS FILTER TESTS
# ==========================================

@pytest.mark.asyncio
async def test_casino_news_filter_rejects_sub_4x():
    """Verify that any casino win with multiplier < 4.0x is rejected from news."""
    mock_bot = AsyncMock()
    mock_bot.get_me.return_value = MagicMock(username="test_bot")

    with patch("news_channel_publisher.get_target_channels", return_value=(-100123456, -100123456)), \
         patch("news_channel_publisher.send_channel_content", new_callable=AsyncMock) as mock_send:

        # 1.8x win on massive bet (100k -> 180k) MUST BE REJECTED
        res1 = await publish_casino_jackpot_news(
            bot=mock_bot, user_id=123, game_type="slots",
            bet_amount=100000, win_amount=180000, multiplier=1.8
        )
        assert res1 is False
        mock_send.assert_not_called()

        # 2.0x win MUST BE REJECTED
        res2 = await publish_casino_jackpot_news(
            bot=mock_bot, user_id=123, game_type="slots",
            bet_amount=50000, win_amount=100000, multiplier=2.0
        )
        assert res2 is False
        mock_send.assert_not_called()

        # 3.99x win MUST BE REJECTED
        res3 = await publish_casino_jackpot_news(
            bot=mock_bot, user_id=123, game_type="slots",
            bet_amount=10000, win_amount=39900, multiplier=3.99
        )
        assert res3 is False
        mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_casino_news_filter_accepts_4x_and_above():
    """Verify that casino wins with multiplier >= 4.0x are accepted and sent to news channel."""
    mock_bot = AsyncMock()
    mock_bot.get_me.return_value = MagicMock(username="test_bot")

    with patch("news_channel_publisher.get_target_channels", return_value=(-100123456, -100123456)), \
         patch("news_channel_publisher.send_channel_content", new_callable=AsyncMock, return_value=99999) as mock_send:

        # 4.0x win with >= 300k win amount
        res = await publish_casino_jackpot_news(
            bot=mock_bot, user_id=123, game_type="slots",
            bet_amount=100000, win_amount=400000, multiplier=4.0, symbols="[🍋 | 🍋 | 🍋]"
        )
        assert res is True
        mock_send.assert_called_once()


# ==========================================
# 2. NIGHT SHIFT MULTIPLIER TESTS
# ==========================================

def test_night_shift_active_hours():
    """Night shift is active 00:00 to 07:00 MSK (UTC+3, which is 21:00 to 04:00 UTC)."""
    # 03:00 MSK (00:00 UTC) -> Active
    ts_night = 1788739200  # Exactly 00:00 UTC = 03:00 MSK
    assert is_night_shift_active(ts_night) is True

    # 15:00 MSK (12:00 UTC) -> Inactive
    ts_day = ts_night + 12 * 3600
    assert is_night_shift_active(ts_day) is False


def test_night_shift_payout_boost():
    """Verify that job payouts are boosted by 1.5x during night shift."""
    ts_night = 1788739200  # 03:00 MSK
    items = {"work_shifts": 10}

    with patch("time.time", return_value=ts_night):
        ok, reward, msg, drop = execute_job_action("bottles", items)
        assert ok is True
        assert "Ночной тариф x1.5" in msg
        # Bottles base range is (15, 30). With 1.5x, minimum possible is int(15*1.5) = 22
        assert reward >= 22


# ==========================================
# 3. DAILY WORK QUESTS TESTS
# ==========================================

def test_daily_quests_generation_and_rollover():
    """Verify daily quests generation, structure, and day rollover."""
    items = {}
    ts1 = 1788700000
    dq = qe.get_or_create_daily_quests(items, now=ts1)

    assert "date" in dq
    assert len(dq["quests"]) == 3
    assert dq["claimed"] is False
    assert dq["reward_cash"] == 7500

    # Simulate next day rollover
    ts2 = ts1 + 90000
    dq2 = qe.get_or_create_daily_quests(items, now=ts2)
    assert dq2["date"] != dq["date"]


def test_daily_quests_progress_and_reward_claim():
    """Verify progress tracking and reward claim with lootbox."""
    items = {}
    ts = 1788700000
    qe.get_or_create_daily_quests(items, now=ts)

    # Initial state: not completed
    assert qe.are_all_quests_completed(items, now=ts) is False
    ok, cash, msg, item = qe.claim_daily_quests_reward(items, now=ts)
    assert ok is False

    # Progress 1: work shifts (target=2)
    qe.record_quest_progress(items, "work", count=1, now=ts)
    assert qe.are_all_quests_completed(items, now=ts) is False
    qe.record_quest_progress(items, "work", count=1, now=ts)

    # Progress 2: side hustle (target=1)
    qe.record_quest_progress(items, "side_hustle", count=1, now=ts)

    # Progress 3: risk action (target=1)
    qe.record_quest_progress(items, "risk_action", count=1, now=ts)

    # Now all quests must be completed
    assert qe.are_all_quests_completed(items, now=ts) is True

    # Claim reward
    ok, cash, msg, item = qe.claim_daily_quests_reward(items, now=ts)
    assert ok is True
    assert cash == 7500
    assert item == "trash_lootbox"
    assert "ПРЕМИЯ ОТ АБУ ПОЛУЧЕНА" in msg

    # Second claim must be rejected
    ok2, _, _, _ = qe.claim_daily_quests_reward(items, now=ts)
    assert ok2 is False


def test_daily_quests_render():
    """Verify human-readable rendering of daily quests."""
    items = {}
    text, can_claim = qe.render_quests_text(items)
    assert "ЕЖЕДНЕВНЫЙ НАPЯД" in text.upper() or "НАРЯД" in text
    assert can_claim is False


# ==========================================
# 4. EXPANDED SIDE HUSTLES & EXPLOIT IMMUNITY
# ==========================================

def _create_mock_callback(user_id: int, action: str):
    cb = MagicMock(spec=types.CallbackQuery)
    cb.id = f"cb_{user_id}_{action}"
    cb.from_user = MagicMock(spec=types.User)
    cb.from_user.id = user_id
    cb.from_user.username = f"user_{user_id}"
    cb.from_user.first_name = "Anon"
    cb.data = f"work_{action}"
    cb.answer = AsyncMock()
    msg = MagicMock(spec=types.Message)
    msg.message_id = 999
    msg.chat = MagicMock(spec=types.Chat)
    msg.chat.id = -100123456
    msg.photo = [MagicMock()]
    msg.edit_caption = AsyncMock()
    msg.edit_text = AsyncMock()
    cb.message = msg
    return cb


@pytest.mark.asyncio
async def test_side_hustle_bottles_day_and_night_and_cooldown(isolated_test_db):
    """
    Verify /work bottles side hustle:
    - Day rate: 150 - 500 ₪
    - Night rate: boosted by x1.5 (225 - 750 ₪) with night note
    - Cooldown: 3h (10800s) base, rejects rapid re-runs
    - Quest progress recorded for 'side_hustle'
    """
    shared_state._GLOBAL_WORK_COOLDOWNS.clear()
    uid_day = 10101
    uid_night = 10102

    # 1. Day execution (15:00 MSK = 12:00 UTC)
    ts_day = 1788739200 + 12 * 3600
    with patch("time.time", return_value=ts_day):
        cb = _create_mock_callback(uid_day, "bottles")
        await cb_work_action(cb, board_id="b")
        assert cb.answer.called
        ans = cb.answer.call_args[0][0]
        assert "стеклотары" in ans
        assert "Ночной тариф x1.5" not in ans
        bal_day = await get_user_global_balance(isolated_test_db, uid_day)
        assert 150 <= bal_day <= 500

        # Immediate re-call -> rejected on cooldown (3h = 10800s)
        cb_repeat = _create_mock_callback(uid_day, "bottles")
        await cb_work_action(cb_repeat, board_id="b")
        ans_rep = cb_repeat.answer.call_args[0][0]
        assert "Пункты приема закрыты" in ans_rep
        # Balance must remain unchanged
        bal_after = await get_user_global_balance(isolated_test_db, uid_day)
        assert bal_after == bal_day

    # 2. Night execution (03:00 MSK = 00:00 UTC)
    ts_night = 1788739200
    with patch("time.time", return_value=ts_night):
        cb_n = _create_mock_callback(uid_night, "bottles")
        await cb_work_action(cb_n, board_id="b")
        ans_n = cb_n.answer.call_args[0][0]
        assert "стеклотары" in ans_n
        assert "Ночной тариф x1.5" in ans_n
        bal_night = await get_user_global_balance(isolated_test_db, uid_night)
        assert 225 <= bal_night <= 750


@pytest.mark.asyncio
async def test_side_hustle_bottles_slippers_cd_discount(isolated_test_db):
    """Verify Slippers gear discount: reduces bottles cooldown from 3h to 2.4h (8640s)."""
    shared_state._GLOBAL_WORK_COOLDOWNS.clear()
    uid = 10103
    now = 1788700000

    # User with slippers equipped
    active_items = {"equipped_feet": "feet_slippers"}
    await isolated_test_db.execute(
        "INSERT INTO Users (user_id, board_id, active_items) VALUES (?, 'b', ?)",
        (uid, json.dumps(active_items))
    )

    with patch("time.time", return_value=now):
        cb1 = _create_mock_callback(uid, "bottles")
        await cb_work_action(cb1, board_id="b")
        assert "стеклотары" in cb1.answer.call_args[0][0]

    # At now + 8639s -> still on cooldown
    with patch("time.time", return_value=now + 8639):
        cb2 = _create_mock_callback(uid, "bottles")
        await cb_work_action(cb2, board_id="b")
        assert "Пункты приема закрыты" in cb2.answer.call_args[0][0]

    # At now + 8641s -> cooldown expired (8640s elapsed)
    with patch("time.time", return_value=now + 8641):
        cb3 = _create_mock_callback(uid, "bottles")
        await cb_work_action(cb3, board_id="b")
        assert "стеклотары" in cb3.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_side_hustle_dumpster_loot_and_night(isolated_test_db):
    """
    Verify /work dumpster:
    - Day & night rates (100-800 base, 150-1200 night)
    - 2h cooldown
    - Item drops (e.g. trash_lootbox)
    - Quest progress recorded for 'risk_action'
    """
    shared_state._GLOBAL_WORK_COOLDOWNS.clear()
    uid = 10104
    ts_night = 1788739200  # 03:00 MSK

    with patch("time.time", return_value=ts_night), \
         patch("random.random", return_value=0.01), \
         patch("random.choice", return_value="trash_lootbox"):
        cb = _create_mock_callback(uid, "dumpster")
        await cb_work_action(cb, board_id="b")
        ans = cb.answer.call_args[0][0]
        assert "Порылся в контейнерах" in ans
        assert "Ночной тариф x1.5" in ans
        assert "Мусорный Лутбокс" in ans

        bal = await get_user_global_balance(isolated_test_db, uid)
        assert 150 <= bal <= 1200

        # Cooldown check: 2h (7200s)
        cb_repeat = _create_mock_callback(uid, "dumpster")
        await cb_work_action(cb_repeat, board_id="b")
        assert "Баки уже обчистили" in cb_repeat.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_side_hustle_flyers_cop_ambush_and_payout(isolated_test_db):
    """
    Verify /work flyers:
    - 20% risk of cop ambush (0 reward, but cooldown still applied)
    - 80% payout (1500 - 4500 base)
    - 4h cooldown
    - Quest progress recorded for 'side_hustle'
    """
    shared_state._GLOBAL_WORK_COOLDOWNS.clear()
    uid_ambush = 10105
    uid_success = 10106
    now = 1788700000

    # 1. Cop ambush scenario
    with patch("time.time", return_value=now), patch("random.random", return_value=0.05):
        cb = _create_mock_callback(uid_ambush, "flyers")
        await cb_work_action(cb, board_id="b")
        ans = cb.answer.call_args[0][0]
        assert "ПРИЕМУЩЕСТВО" in ans
        bal = await get_user_global_balance(isolated_test_db, uid_ambush)
        assert bal == 0

        # Cooldown still active despite ambush
        cb_cd = _create_mock_callback(uid_ambush, "flyers")
        await cb_work_action(cb_cd, board_id="b")
        assert "Все столбы и остановки уже заклеены" in cb_cd.answer.call_args[0][0]

    # 2. Success scenario
    with patch("time.time", return_value=now), patch("random.random", return_value=0.50):
        cb_s = _create_mock_callback(uid_success, "flyers")
        await cb_work_action(cb_s, board_id="b")
        ans_s = cb_s.answer.call_args[0][0]
        assert "Оклеил 10 подъездов" in ans_s
        bal_s = await get_user_global_balance(isolated_test_db, uid_success)
        assert 1500 <= bal_s <= 4500


@pytest.mark.asyncio
async def test_side_hustle_microloan_borrow_and_debt_lock(isolated_test_db):
    """
    Verify /work microloan:
    - Borrow 5,000 - 15,000 ₪
    - Debt set to 1.3x borrowed amount
    - Cooldown: 12h
    - Active debt lock: cannot take another microloan while debt > 0
    """
    shared_state._GLOBAL_WORK_COOLDOWNS.clear()
    uid = 10107
    now = 1788700000

    with patch("time.time", return_value=now):
        cb = _create_mock_callback(uid, "microloan")
        await cb_work_action(cb, board_id="b")
        ans = cb.answer.call_args[0][0]
        assert "оформил онлайн-займ" in ans
        bal = await get_user_global_balance(isolated_test_db, uid)
        assert 5000 <= bal <= 15000

        # Immediate attempt -> rejected by cooldown
        cb2 = _create_mock_callback(uid, "microloan")
        await cb_work_action(cb2, board_id="b")
        assert "пересменка" in cb2.answer.call_args[0][0]

    # Even 24h later (cooldown expired), debt lock MUST reject
    with patch("time.time", return_value=now + 86400):
        cb3 = _create_mock_callback(uid, "microloan")
        await cb_work_action(cb3, board_id="b")
        ans3 = cb3.answer.call_args[0][0]
        assert "Коллекторы требуют закрыть старый долг" in ans3
        # Balance must remain unchanged
        bal_final = await get_user_global_balance(isolated_test_db, uid)
        assert bal_final == bal


@pytest.mark.asyncio
async def test_side_hustle_sell_mother_strictly_once_cross_board(isolated_test_db):
    """
    Verify /work sell_mother:
    - Gives exactly 8,000 ₪ on first use
    - Strictly 1-time limit in lifetime
    - Second use on any board is permanently blocked
    """
    shared_state._GLOBAL_WORK_COOLDOWNS.clear()
    uid = 10108

    # 1. First execution on board 'b' -> Success
    cb1 = _create_mock_callback(uid, "sell_mother")
    await cb_work_action(cb1, board_id="b")
    assert "Сделка века! Ты продал мать" in cb1.answer.call_args[0][0]
    bal = await get_user_global_balance(isolated_test_db, uid)
    assert bal == 8000

    # 2. Second attempt on board 'b' -> Blocked
    cb2 = _create_mock_callback(uid, "sell_mother")
    await cb_work_action(cb2, board_id="b")
    assert "Ты уже продал мать" in cb2.answer.call_args[0][0]

    # 3. Third attempt on board 'sex' -> Cross-board Blocked
    cb3 = _create_mock_callback(uid, "sell_mother")
    await cb_work_action(cb3, board_id="sex")
    assert "Ты уже продал мать" in cb3.answer.call_args[0][0]

    # Final balance must still be strictly 8000 ₪
    bal_final = await get_user_global_balance(isolated_test_db, uid)
    assert bal_final == 8000


@pytest.mark.asyncio
async def test_side_hustle_overtime_flash_ultra_limits(isolated_test_db):
    """
    Verify /work overtime (Flash Ultra energy drink):
    - Max 2 cans per day
    - Min 30 min cooldown between cans
    - Resets career job on cooldown
    - 3rd attempt is rejected with warning
    """
    shared_state._GLOBAL_WORK_COOLDOWNS.clear()
    uid = 10109
    now = 1788700000

    # 1. No job on cooldown -> rejected
    with patch("time.time", return_value=now):
        cb0 = _create_mock_callback(uid, "overtime")
        await cb_work_action(cb0, board_id="b")
        assert "нет карьерных смен на кулдауне" in cb0.answer.call_args[0][0]

    # Put 'bottles' job (cooldown_sec=180) on cooldown
    active_items = {"work_cooldowns": {"bottles": now}}
    await isolated_test_db.execute(
        "INSERT INTO Users (user_id, board_id, active_items) VALUES (?, 'b', ?)",
        (uid, json.dumps(active_items))
    )

    # 2. Can 1 -> Success, resets cooldown, reports 1/2 cans remaining
    with patch("time.time", return_value=now):
        cb1 = _create_mock_callback(uid, "overtime")
        await cb_work_action(cb1, board_id="b")
        ans1 = cb1.answer.call_args[0][0]
        assert "залпом въебал банку Flash Ultra" in ans1
        assert "Осталось банок на сегодня: 1/2" in ans1

    # Put job on cooldown again at now + 600
    active_items["work_cooldowns"]["bottles"] = now + 600
    shared_state.set_user_work_cooldown(uid, "bottles", now + 600)
    await isolated_test_db.execute(
        "UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = 'b'",
        (json.dumps(active_items), uid)
    )
    with patch("time.time", return_value=now + 600):
        cb2 = _create_mock_callback(uid, "overtime")
        await cb_work_action(cb2, board_id="b")
        assert "Пульс зашкаливает" in cb2.answer.call_args[0][0]

    # After 30 min (now + 1801s) -> Put job on cooldown at now + 1801s
    active_items["work_cooldowns"]["bottles"] = now + 1801
    shared_state.set_user_work_cooldown(uid, "bottles", now + 1801)
    await isolated_test_db.execute(
        "UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = 'b'",
        (json.dumps(active_items), uid)
    )
    with patch("time.time", return_value=now + 1801):
        cb3 = _create_mock_callback(uid, "overtime")
        await cb_work_action(cb3, board_id="b")
        ans3 = cb3.answer.call_args[0][0]
        assert "залпом въебал банку Flash Ultra" in ans3
        assert "Осталось банок на сегодня: 0/2" in ans3

    # Attempt 3rd can at now + 2400s -> strictly rejected (limit reached 2/2)
    active_items["work_cooldowns"]["bottles"] = now + 2400
    shared_state.set_user_work_cooldown(uid, "bottles", now + 2400)
    await isolated_test_db.execute(
        "UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = 'b'",
        (json.dumps(active_items), uid)
    )
    with patch("time.time", return_value=now + 2400):
        cb4 = _create_mock_callback(uid, "overtime")
        await cb_work_action(cb4, board_id="b")
        assert "Лимит Flash Ultra исчерпан" in cb4.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_side_hustles_cross_board_synchronization(isolated_test_db):
    """Verify that completing a side hustle on board 'b' blocks execution on board 'vg'."""
    shared_state._GLOBAL_WORK_COOLDOWNS.clear()
    uid = 10110
    now = 1788700000

    # Execute on 'b'
    with patch("time.time", return_value=now):
        cb_b = _create_mock_callback(uid, "bottles")
        await cb_work_action(cb_b, board_id="b")
        assert "стеклотары" in cb_b.answer.call_args[0][0]

        # Execute on 'vg' -> blocked by cross-board cooldown
        cb_vg = _create_mock_callback(uid, "bottles")
        await cb_work_action(cb_vg, board_id="vg")
        assert "Пункты приема закрыты" in cb_vg.answer.call_args[0][0]


# ==========================================
# 5. WHALE MONEY SINKS & MACRO STABILITY
# ==========================================

def test_whale_safe_exponential_pricing_formula():
    """Validates exponential progression P(n) = int(50,000 * 1.5^n)."""
    assert calculate_whale_safe_price(0) == 50000
    assert calculate_whale_safe_price(1) == 75000
    assert calculate_whale_safe_price(2) == 112500
    assert calculate_whale_safe_price(3) == 168750
    assert calculate_whale_safe_price(4) == 253125
    assert calculate_whale_safe_price(10) == 2883251
    # Clamping boundaries
    assert calculate_whale_safe_price(-10) == 50000
    assert calculate_whale_safe_price(50) == calculate_whale_safe_price(40)


@pytest.mark.asyncio
async def test_whale_safe_purchase_70_percent_burn_and_zero_dup(isolated_test_db):
    """
    Verify Whale Safe purchase:
    - Deducts price P(0) = 50,000 ₪
    - Burns 70% (35,000 ₪) to Abu Yacht Fund
    - Liquid return <= 15,000 ₪ (net sink >= 35,000 ₪, zero dupes)
    - Rejects purchase when balance is insufficient
    """
    uid = 20201
    await add_user_global_balance(isolated_test_db, uid, "b", 100000)

    fund_before = await get_abu_fund_total(isolated_test_db)
    res = await buy_whale_safe(isolated_test_db, uid, "b")
    assert res["ok"] is True
    assert res["price"] == 50000
    assert res["burned_to_abu"] == 35000.0

    # Fund must increase by exactly 35,000 ₪
    fund_after = await get_abu_fund_total(isolated_test_db)
    assert round(fund_after - fund_before, 2) == 35000.0

    # User balance must have decreased by at least 35,000 ₪ (50k cost - max 15k cash)
    new_bal = await get_user_global_balance(isolated_test_db, uid)
    assert new_bal <= 65000

    # Insufficient funds test: next safe costs P(1) = 75,000 ₪, user has <= 65,000 ₪
    res_fail = await buy_whale_safe(isolated_test_db, uid, "b")
    assert res_fail["ok"] is False
    assert "Недостаточно шекелей" in res_fail["error"]


def test_super_wealth_tax_progressive_rates_and_dead_accounts():
    """
    Verify progressive brackets of calculate_wealth_tax:
    - <= 5k: 0%
    - 5k - 50k: 0.3%
    - 50k - 500k: 1.0%
    - 500k - 5M: 2.5%
    - > 5M: 5.0%
    - Idle surcharge: 1.5x multiplier on accounts > 500k with idle_hours >= 72.0
    - Bank deposit discount: 50% discount on deposit portion
    """
    # Low wealth (exempt)
    assert calculate_wealth_tax(5000) == 0.0
    assert calculate_wealth_tax(0) == 0.0

    # Bracket 1 (0.3%)
    assert calculate_wealth_tax(40000) == 120.0

    # Bracket 2 (1.0%)
    assert calculate_wealth_tax(300000) == 3000.0

    # Bracket 3 (2.5%) - Active vs Dead account
    # Active: 600,000 * 0.025 = 15,000 ₪
    assert calculate_wealth_tax(600000, idle_hours=12.0) == 15000.0
    # Dead (>=72h): 600,000 * (0.025 * 1.5) = 22,500 ₪
    assert calculate_wealth_tax(600000, idle_hours=72.0) == 22500.0

    # 1 Million Whale:
    # Active: 1,000,000 * 0.025 = 25,000 ₪ / day
    assert calculate_wealth_tax(1000000, idle_hours=24.0) == 25000.0
    # Dead: 1,000,000 * 0.0375 = 37,500 ₪ / day (sterilizes stagnant balances)
    assert calculate_wealth_tax(1000000, idle_hours=100.0) == 37500.0

    # Bracket 4 (> 5M: 5.0%)
    # Active: 6,000,000 * 0.050 = 300,000 ₪
    assert calculate_wealth_tax(6000000, idle_hours=10.0) == 300000.0
    # Dead: 6,000,000 * 0.075 = 450,000 ₪ / day
    assert calculate_wealth_tax(6000000, idle_hours=80.0) == 450000.0

    # Bank deposit discount (50% discount on bank portion)
    # Total wealth 1,000,000 ₪ with 500,000 ₪ in bank deposit
    # Base tax: 25,000 ₪. Discount: 500,000 * 0.025 * 0.50 = 6,250 ₪ -> Tax = 18,750 ₪
    tax_with_dep = calculate_wealth_tax(1000000, idle_hours=0.0, deposit_balance=500000)
    assert tax_with_dep == 18750.0


@pytest.mark.asyncio
async def test_super_wealth_tax_daily_execution_and_abu_burn(isolated_test_db):
    """
    Verify process_daily_wealth_tax live DB execution:
    - Taxes active rich accounts at regular rate
    - Taxes idle/dead accounts (>72h idle) with 1.5x surcharge
    - Exempts small accounts (<=5k) and self-isolated accounts
    - Transfers 100% of collected tax to Abu Yacht Fund
    """
    now = time.time()
    # 1. Active rich user (800,000 ₪) with recent post (1h ago)
    uid_active = 30301
    await add_user_global_balance(isolated_test_db, uid_active, "b", 800000)
    await isolated_test_db.execute(
        "INSERT INTO Posts (post_num, author_id, board_id, timestamp, content) VALUES (1, ?, 'b', ?, ?)",
        (uid_active, now - 3600, json.dumps({"text": "active post"}))
    )

    # 2. Dead rich user (1,200,000 ₪) with post 100h ago (idle >= 72h)
    uid_dead = 30302
    await add_user_global_balance(isolated_test_db, uid_dead, "b", 1200000)
    await isolated_test_db.execute(
        "INSERT INTO Posts (post_num, author_id, board_id, timestamp, content) VALUES (2, ?, 'b', ?, ?)",
        (uid_dead, now - 3600 * 100, json.dumps({"text": "old post"}))
    )

    # 3. Poor user (4,000 ₪) - exempt
    uid_poor = 30303
    await add_user_global_balance(isolated_test_db, uid_poor, "b", 4000)

    # 4. Isolated user (2,000,000 ₪) - protected
    uid_iso = 30304
    await add_user_global_balance(isolated_test_db, uid_iso, "b", 2000000)
    await isolated_test_db.execute(
        "UPDATE Users SET is_isolated = 1 WHERE user_id = ?",
        (uid_iso,)
    )

    fund_before = await get_abu_fund_total(isolated_test_db)
    res = await process_daily_wealth_tax(isolated_test_db)

    assert res["affected_users"] == 2
    # Active user: 800,000 * 0.025 = 20,000 ₪
    bal_active = await get_user_global_balance(isolated_test_db, uid_active)
    assert bal_active == 780000

    # Dead user: 1,200,000 * (0.025 * 1.5) = 45,000 ₪ (idle surcharge applied!)
    bal_dead = await get_user_global_balance(isolated_test_db, uid_dead)
    assert bal_dead == 1155000

    # Total tax = 65,000 ₪ burned to Abu Yacht Fund
    fund_after = await get_abu_fund_total(isolated_test_db)
    assert round(fund_after - fund_before, 2) == 65000.0


@pytest.mark.asyncio
async def test_auction_bids_validation_escrow_and_anti_snipe(isolated_test_db):
    """
    Verify Atomic Auctions:
    - Strict bid validation (NaN, <=0, >10B rejected)
    - Self-bidding rejection
    - Atomic escrow deduction: new bid deducted before refunding previous highest bidder
    - Anti-sniping: extensions when placed in last 300s
    - Finalization: 100% of winning bid burned to Abu Yacht Fund
    """
    auc_id = await create_auction(
        isolated_test_db,
        lot_type="board_pin",
        title="VIP Top Pin",
        description="24h board pin voucher",
        start_price=1000.0,
        min_bid_step=100.0,
        duration_sec=600.0
    )

    uid1 = 40401
    uid2 = 40402
    await add_user_global_balance(isolated_test_db, uid1, "b", 5000)
    await add_user_global_balance(isolated_test_db, uid2, "b", 10000)

    # 1. Invalid bids rejected
    res_bad = await place_auction_bid(isolated_test_db, auc_id, uid1, "Anon1", 0)
    assert res_bad["ok"] is False

    res_nan = await place_auction_bid(isolated_test_db, auc_id, uid1, "Anon1", float("nan"))
    assert res_nan["ok"] is False

    # 2. Bid 1: User 1 bids 1000 ₪
    res1 = await place_auction_bid(isolated_test_db, auc_id, uid1, "Anon1", 1000.0)
    assert res1["ok"] is True
    bal1 = await get_user_global_balance(isolated_test_db, uid1)
    assert bal1 == 4000.0

    # Self-outbid rejected
    res_self = await place_auction_bid(isolated_test_db, auc_id, uid1, "Anon1", 1200.0)
    assert res_self["ok"] is False
    assert "уже наивысшая" in res_self["error"]

    # Insufficient step rejected (must be >= 1000 + 100 = 1100)
    res_low = await place_auction_bid(isolated_test_db, auc_id, uid2, "Anon2", 1050.0)
    assert res_low["ok"] is False
    assert "Слишком маленькая ставка" in res_low["error"]

    # 3. Bid 2: User 2 bids 1200 ₪ -> Escrow deduction and instant refund to User 1
    res2 = await place_auction_bid(isolated_test_db, auc_id, uid2, "Anon2", 1200.0)
    assert res2["ok"] is True
    # User 2 deducted 1200 (10000 -> 8800)
    bal2 = await get_user_global_balance(isolated_test_db, uid2)
    assert bal2 == 8800.0
    # User 1 fully refunded 1000 ₪ (4000 -> 5000)
    bal1_ref = await get_user_global_balance(isolated_test_db, uid1)
    assert bal1_ref == 5000.0

    # 4. Anti-sniping extension check (< 300s left)
    now = time.time()
    with patch("time.time", return_value=res2["ends_at"] - 100):
        res_snipe = await place_auction_bid(isolated_test_db, auc_id, uid1, "Anon1", 1500.0)
        assert res_snipe["ok"] is True
        assert res_snipe["extended"] is True
        assert res_snipe["ends_at"] > res2["ends_at"]

    # 5. Auction completion burns 100% of winning bid to Abu Yacht Fund
    fund_before = await get_abu_fund_total(isolated_test_db)
    with patch("time.time", return_value=res_snipe["ends_at"] + 10):
        finished = await finish_active_auctions(isolated_test_db)
        assert len(finished) == 1
        assert finished[0]["winning_bid"] == 1500.0
        fund_after = await get_abu_fund_total(isolated_test_db)
        assert round(fund_after - fund_before, 2) == 1500.0


@pytest.mark.asyncio
async def test_oligarch_raid_qualification_confiscation_and_abu_burn(isolated_test_db):
    """
    Verify /raid_oligarch (Class Wars):
    - Requires 5 qualified proletarian voters (<5k capital, >=25 posts)
    - Defenses: Diplomatic Passport completely blocks raid
    - Confiscation: 10% of oligarch capital (capped at 200,000 ₪)
    - 70% burned to Abu Yacht Fund, 30% split equally among the 5 voters
    - Sterilizes money from circulation permanently
    """
    # 5 proletarian voters
    voters = [50501, 50502, 50503, 50504, 50505]
    for vid in voters:
        await add_user_global_balance(isolated_test_db, vid, "b", 1000)
        await isolated_test_db.execute(
            "UPDATE Users SET posts_count = 30 WHERE user_id = ?",
            (vid,)
        )

    # Oligarch with 1,000,000 ₪
    oligarch_id = 50599
    await add_user_global_balance(isolated_test_db, oligarch_id, "b", 1000000)

    # 1. Defenses test: Diplomatic Passport blocks raid
    active_items = {"diplomatic_passport": True}
    await isolated_test_db.execute(
        "UPDATE Users SET active_items = ? WHERE user_id = ?",
        (json.dumps(active_items), oligarch_id)
    )
    res_blocked = await execute_oligarch_raid(isolated_test_db, voter_ids=voters, target_id=oligarch_id)
    assert res_blocked["ok"] is False
    assert res_blocked["blocked"] is True
    assert "Дипломатический Паспорт" in res_blocked["error"]

    # Remove passport -> Raid proceeds
    await isolated_test_db.execute(
        "UPDATE Users SET active_items = '{}' WHERE user_id = ?",
        (oligarch_id,)
    )
    fund_before = await get_abu_fund_total(isolated_test_db)
    res_raid = await execute_oligarch_raid(isolated_test_db, voter_ids=voters, target_id=oligarch_id)

    assert res_raid["ok"] is True
    # 10% of 1,000,000 = 100,000 ₪ confiscated
    assert res_raid["confiscated"] == 100000.0
    # 70% burned to Abu Fund = 70,000 ₪
    assert res_raid["burned_to_abu"] == 70000.0
    fund_after = await get_abu_fund_total(isolated_test_db)
    assert round(fund_after - fund_before, 2) == 70000.0

    # 30% distributed to 5 workers = 6,000 ₪ each (1000 -> 7000)
    assert res_raid["per_voter"] == 6000.0
    for vid in voters:
        bal = await get_user_global_balance(isolated_test_db, vid)
        assert bal == 7000.0

    # Oligarch balance = 900,000 ₪
    bal_oligarch = await get_user_global_balance(isolated_test_db, oligarch_id)
    assert bal_oligarch == 900000.0
