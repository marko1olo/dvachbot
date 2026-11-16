# -*- coding: utf-8 -*-
"""
tests/test_heist_laundering_loans.py — Unit & Integration Test Suite for
Heist Event, Dirty Money Laundering & Loan Shark Engine.
"""

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import aiosqlite

import common.config
import common.database
import common.db_pool

from heist_and_loan_engine import (
    heist_loan_router,
    get_user_active_items,
    save_user_active_items,
    process_money_laundering,
    count_user_combat_gear,
    calculate_heist_win_chance,
    HeistLobby,
    active_heist_lobbies,
    chat_active_heist,
    build_heist_keyboard,
    resolve_heist,
    check_and_apply_loan_penalty,
    garnish_wages_for_loan,
    process_borrow_loan,
    process_repay_debt,
    cb_heist_join,
    cb_heist_start,
    cmd_money_laundering,
    cmd_start_heist,
    cmd_loan,
    cmd_paydebt,
    build_loan_keyboard,
    format_loan_menu_text,
    build_launder_keyboard,
    format_launder_menu_text,
    cb_loan_hub,
    cb_loan_take_preset,
    cb_loan_paydebt_full,
    cb_launder_hub,
    cb_launder_do_all,
    cb_launder_do_half,
)
from common.criminal_phrases import (
    HEIST_WIN_PHRASES,
    HEIST_LOSE_PHRASES,
    LOAN_PAKHOM_COLLECTOR_PHRASES,
    LAUNDER_WASHER_PHRASES,
)
from help_text import (
    get_help_hub_page,
    HELP_HUB_PAGES_RU,
    HELP_HUB_PAGES_EN,
    HELP_HUB_PAGES_JP,
)


@pytest.fixture(autouse=True)
def clear_heist_lobbies():
    active_heist_lobbies.clear()
    chat_active_heist.clear()
    yield
    active_heist_lobbies.clear()
    chat_active_heist.clear()


# =============================================================================
# SYSTEM 1: MONEY LAUNDERING TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_launder_zero_or_negative_dirty_balance(isolated_test_db):
    db = isolated_test_db
    user_id = 1001
    active_items = {"dirty_balance": 0.0}

    success, msg, data = await process_money_laundering(db, user_id, "all", active_items=active_items)
    assert success is False
    assert "У тебя нет меченых шекелей" in msg
    assert data["dirty_balance"] == 0.0


@pytest.mark.asyncio
async def test_launder_full_amount_70_30_split(isolated_test_db):
    db = isolated_test_db
    user_id = 1002
    board_id = "b"

    # Setup 100,000 dirty balance
    active_items = {"dirty_balance": 100_000.0}
    await save_user_active_items(db, user_id, active_items, board_id)

    fund_before = await common.database.get_abu_fund_total(db)
    bal_before = await common.database.get_user_global_balance(db, user_id)

    success, msg, data = await process_money_laundering(db, user_id, "all", board_id=board_id)
    assert success is True

    # 30% fee, 70% clean
    assert data["amount_laundered"] == 100_000
    assert data["clean"] == 70_000
    assert data["fee"] == 30_000
    assert data["remaining_dirty"] == 0.0

    # Verify message matches specification
    assert "ТЕНЕВАЯ ПРАЧЕЧНАЯ АБУ" in msg
    assert "30% (30,000 ₪) отжато на яхту" in msg
    assert "70,000 ₪ легли в карман чистыми белыми купюрами" in msg

    # Verify DB balances
    fund_after = await common.database.get_abu_fund_total(db)
    bal_after = await common.database.get_user_global_balance(db, user_id)
    assert fund_after - fund_before == 30_000.0
    assert bal_after - bal_before == 70_000.0

    # Verify active_items updated in DB
    updated_items = await get_user_active_items(db, user_id, board_id)
    assert updated_items.get("dirty_balance") == 0.0


@pytest.mark.asyncio
async def test_launder_partial_amount(isolated_test_db):
    db = isolated_test_db
    user_id = 1003
    board_id = "b"

    active_items = {"dirty_balance": 50_000.0}
    await save_user_active_items(db, user_id, active_items, board_id)

    fund_before = await common.database.get_abu_fund_total(db)
    bal_before = await common.database.get_user_global_balance(db, user_id)

    # Launder 20,000 out of 50,000
    success, msg, data = await process_money_laundering(db, user_id, "20000", board_id=board_id)
    assert success is True
    assert data["amount_laundered"] == 20_000
    assert data["clean"] == 14_000  # 70%
    assert data["fee"] == 6_000     # 30%
    assert data["remaining_dirty"] == 30_000.0

    fund_after = await common.database.get_abu_fund_total(db)
    bal_after = await common.database.get_user_global_balance(db, user_id)
    assert fund_after - fund_before == 6_000.0
    assert bal_after - bal_before == 14_000.0

    updated_items = await get_user_active_items(db, user_id, board_id)
    assert updated_items.get("dirty_balance") == 30_000.0


@pytest.mark.asyncio
async def test_launder_more_than_dirty_balance(isolated_test_db):
    db = isolated_test_db
    user_id = 1004
    active_items = {"dirty_balance": 10_000.0}

    success, msg, data = await process_money_laundering(db, user_id, 25_000, active_items=active_items)
    assert success is False
    assert "нет столько меченых шекелей" in msg
    assert active_items["dirty_balance"] == 10_000.0


@pytest.mark.asyncio
async def test_launder_invalid_amount_spec(isolated_test_db):
    db = isolated_test_db
    user_id = 1005
    active_items = {"dirty_balance": 10_000.0}

    success, msg, _ = await process_money_laundering(db, user_id, "непонятно_что", active_items=active_items)
    assert success is False
    assert "корректную сумму" in msg


# =============================================================================
# SYSTEM 2: BANK ARMORED TRUCK HEIST TESTS
# =============================================================================

def test_heist_combat_math_gear_scaling():
    # Base chance without gear = 45% (0.45)
    chance_0 = calculate_heist_win_chance([{}, {}])
    assert chance_0 == 0.45

    # 1 gear item (+5%) = 50% (0.50)
    crew_gear_1 = [{"equipped_weapon": "shit_gun"}, {}]
    assert calculate_heist_win_chance(crew_gear_1) == 0.50

    # 4 gear items (+20%) = 65% (0.65)
    crew_gear_4 = [
        {"equipped_weapon": "shit_gun", "equipped_armor": "body_armor"},
        {"combat_gear_count": 2}
    ]
    assert calculate_heist_win_chance(crew_gear_4) == 0.65

    # 6 gear items (+30%) = 75% (0.75) (Max cap)
    crew_gear_6 = [{"combat_gear_count": 6}]
    assert calculate_heist_win_chance(crew_gear_6) == 0.75

    # 10 gear items -> capped at 75% (0.75)
    crew_gear_10 = [{"combat_gear_count": 10}]
    assert calculate_heist_win_chance(crew_gear_10) == 0.75


def test_heist_lobby_creation_and_keyboard():
    lobby = HeistLobby(
        lobby_id="test_heist_1",
        chat_id=12345,
        initiator_id=2001,
        initiator_name="Анон Главать",
        board_id="b"
    )
    assert len(lobby.participants) == 1
    assert lobby.status == "open"

    # Verify initial button is [🦹 Вступить в банду (1/4)]
    kb = build_heist_keyboard(lobby)
    btn = kb.inline_keyboard[0][0]
    assert "Вступить в банду (1/4)" in btn.text
    assert btn.callback_data == "heist_join:test_heist_1"
    # No start button yet (needs >= 2 participants)
    assert len(kb.inline_keyboard) == 1

    # Add second participant
    lobby.participants.append(2002)
    lobby.participant_names[2002] = "Анон Стрелок"
    kb2 = build_heist_keyboard(lobby)
    assert "Вступить в банду (2/4)" in kb2.inline_keyboard[0][0].text
    # Start button is now visible
    assert len(kb2.inline_keyboard) == 2
    assert "Начать налёт сейчас" in kb2.inline_keyboard[1][0].text


@pytest.mark.asyncio
async def test_heist_crew_size_requirement_cancel(isolated_test_db):
    db = isolated_test_db
    lobby_id = "test_heist_cancel"
    lobby = HeistLobby(
        lobby_id=lobby_id,
        chat_id=10001,
        initiator_id=2001,
        initiator_name="Одинокий Сыч",
        board_id="b"
    )
    active_heist_lobbies[lobby_id] = lobby

    # Only 1 participant -> heist cancelled
    res = await resolve_heist(lobby_id, db=db)
    assert res["status"] == "cancelled"
    assert res["reason"] == "not_enough_participants"


@pytest.mark.asyncio
async def test_heist_win_outcome_dirty_balance_split_and_stars(isolated_test_db):
    db = isolated_test_db
    board_id = "b"
    crew = [3001, 3002, 3003]

    # Initialize participants
    for uid in crew:
        await save_user_active_items(db, uid, {"dirty_balance": 0.0, "wanted_stars": 0, "bounty": 0}, board_id)

    lobby_id = "test_heist_win"
    lobby = HeistLobby(
        lobby_id=lobby_id,
        chat_id=10002,
        initiator_id=crew[0],
        initiator_name="Главарь",
        board_id=board_id
    )
    lobby.participants = list(crew)
    for uid in crew:
        lobby.participant_names[uid] = f"Боец {uid}"
    active_heist_lobbies[lobby_id] = lobby

    # Force win with 600,000 loot pool (200,000 per member)
    res = await resolve_heist(lobby_id, db=db, force_win=True, custom_loot_pool=600_000)
    assert res["status"] == "won"
    assert res["loot_pool"] == 600_000
    assert res["per_member"] == 200_000

    # Verify each member got dirty_balance, +2 wanted stars, +10,000 bounty
    for uid in crew:
        items = await get_user_active_items(db, uid, board_id)
        assert items["dirty_balance"] == 200_000.0
        assert items["wanted_stars"] == 2
        assert items["bounty"] == 10_000


@pytest.mark.asyncio
async def test_heist_loss_outcome_mute_and_fine(isolated_test_db):
    db = isolated_test_db
    board_id = "b"
    p1 = 4001
    p2 = 4002

    # Give clean balances: p1 = 10,000 ₪, p2 = 20,000 ₪
    await common.database.add_user_global_balance(db, p1, board_id, 10_000.0)
    await common.database.add_user_global_balance(db, p2, board_id, 20_000.0)
    await save_user_active_items(db, p1, {}, board_id)
    await save_user_active_items(db, p2, {}, board_id)

    fund_before = await common.database.get_abu_fund_total(db)

    lobby_id = "test_heist_loss"
    lobby = HeistLobby(
        lobby_id=lobby_id,
        chat_id=10003,
        initiator_id=p1,
        initiator_name="Неудачник 1",
        board_id=board_id
    )
    lobby.participants = [p1, p2]
    lobby.participant_names[p1] = "Неудачник 1"
    lobby.participant_names[p2] = "Неудачник 2"
    active_heist_lobbies[lobby_id] = lobby

    # Force lose
    res = await resolve_heist(lobby_id, db=db, force_win=False)
    assert res["status"] == "lost"

    # Verify 15% fine confiscation
    # 15% of 10,000 = 1,500
    # 15% of 20,000 = 3,000
    bal_p1 = await common.database.get_user_global_balance(db, p1)
    bal_p2 = await common.database.get_user_global_balance(db, p2)
    assert bal_p1 == 8_500.0
    assert bal_p2 == 17_000.0

    # Verify Abu Fund received the confiscated fines (1500 + 3000 = 4500)
    fund_after = await common.database.get_abu_fund_total(db)
    assert fund_after - fund_before == 4_500.0

    # Verify both participants are muted in Mutes table
    now_ts = time.time()
    for uid in (p1, p2):
        async with db.execute(
            "SELECT expires_at FROM Mutes WHERE user_id = ? AND mute_type = 'mute'",
            (uid,)
        ) as cur:
            row = await cur.fetchone()
            assert row is not None
            assert row[0] > now_ts + 3000  # ~3600 seconds


# =============================================================================
# SYSTEM 3: LOAN SHARK / MICROLOAN TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_loan_borrow_constraints(isolated_test_db):
    db = isolated_test_db
    board_id = "b"
    uid = 5001

    # 1. Clean balance > 500 ₪ is rejected
    await common.database.add_user_global_balance(db, uid, board_id, 800.0)
    ok, err_msg, _ = await process_borrow_loan(db, uid, 1000, board_id=board_id)
    assert ok is False
    assert "балансом до 500 ₪" in err_msg

    # 2. Set balance to 200 ₪ -> eligible!
    await common.database.deduct_user_global_balance(db, uid, board_id, 600.0)

    # Invalid amount: < 500 ₪
    ok, err_msg, _ = await process_borrow_loan(db, uid, 400, board_id=board_id)
    assert ok is False
    assert "500 ₪" in err_msg and "5,000 ₪" in err_msg

    # Invalid amount: > 5000 ₪
    ok, err_msg, _ = await process_borrow_loan(db, uid, 6000, board_id=board_id)
    assert ok is False
    assert "500 ₪" in err_msg and "5,000 ₪" in err_msg

    # 3. Valid loan borrow: 1,000 ₪
    now = time.time()
    ok, contract_msg, data = await process_borrow_loan(db, uid, 1000, board_id=board_id)
    assert ok is True
    assert data["amount"] == 1000
    assert data["owed"] == 1200  # 20% flat interest
    assert data["due_at"] >= now + 86300

    # User clean balance should now be 200 + 1000 = 1200
    bal = await common.database.get_user_global_balance(db, uid)
    assert bal == 1200.0

    # Check active_items in DB
    items = await get_user_active_items(db, uid, board_id)
    assert items["loan_amount"] == 1000
    assert items["loan_owed"] == 1200
    assert items["is_defaulter"] is False

    # 4. Attempting to borrow again while loan is active is rejected
    ok2, err2, _ = await process_borrow_loan(db, uid, 1000, board_id=board_id)
    assert ok2 is False
    assert "прошлый долг не закрыл" in err2


@pytest.mark.asyncio
async def test_loan_paydebt_on_time_success(isolated_test_db):
    db = isolated_test_db
    board_id = "b"
    uid = 5002

    # User borrows 2,000 ₪ -> owes 2,400 ₪
    await process_borrow_loan(db, uid, 2000, board_id=board_id)

    # Give user extra shekels to be able to pay (total balance 3,000 ₪)
    await common.database.add_user_global_balance(db, uid, board_id, 1000.0)
    bal_before = await common.database.get_user_global_balance(db, uid)
    assert bal_before == 3000.0

    # Repay
    ok, msg, data = await process_repay_debt(db, uid, board_id=board_id)
    assert ok is True
    assert data["repaid"] == 2400
    assert data["credit_rating"] == 110  # Increased rating
    assert "ПАХОМ ДОВОЛЕН" in msg

    # Balance after repayment: 3000 - 2400 = 600
    bal_after = await common.database.get_user_global_balance(db, uid)
    assert bal_after == 600.0

    # Debt cleared
    items = await get_user_active_items(db, uid, board_id)
    assert items["loan_owed"] == 0
    assert items["is_defaulter"] is False


@pytest.mark.asyncio
async def test_loan_paydebt_insufficient_funds(isolated_test_db):
    db = isolated_test_db
    board_id = "b"
    uid = 5003

    # User owes 1,200 ₪ but only has 1,000 ₪
    await process_borrow_loan(db, uid, 1000, board_id=board_id)

    # Repay fails
    ok, msg, _ = await process_repay_debt(db, uid, board_id=board_id)
    assert ok is False
    assert "недостаточно шекелей" in msg

    items = await get_user_active_items(db, uid, board_id)
    assert items["loan_owed"] == 1200


def test_loan_overdue_default_enforcement_and_harassment():
    now = time.time()
    # Loan due 1 hour ago
    active_items = {
        "loan_amount": 1000,
        "loan_owed": 1200,
        "loan_due_at": now - 3600,
        "is_defaulter": False
    }

    is_penalized, harassment_text = check_and_apply_loan_penalty(active_items, current_time=now)
    assert is_penalized is True
    assert active_items["is_defaulter"] is True
    assert "Счётчик тикает, чепуха!" in harassment_text
    assert "Пахом прислал коллекторов" in harassment_text
    assert "75% зарплаты на /work" in harassment_text


def test_loan_wage_garnishment_calculation():
    now = time.time()
    active_items = {
        "loan_amount": 2000,
        "loan_owed": 2400,
        "loan_due_at": now - 100,
        "is_defaulter": True
    }

    # Worker earns 1,000 ₪ on /work
    # 75% garnished = 750 ₪
    # Net wage to user = 250 ₪
    # Remaining debt = 2400 - 750 = 1650 ₪
    net_wage, garnished, notice = garnish_wages_for_loan(active_items, wage=1000.0, current_time=now)
    assert garnished == 750.0
    assert net_wage == 250.0
    assert active_items["loan_owed"] == 1650.0
    assert active_items["is_defaulter"] is True
    assert "КОЛЛЕКТОРЫ ПАХОМА ОТОБРАЛИ 750 ₪" in notice

    # Next job: earns 3,000 ₪
    # 75% of 3000 is 2250, but remaining debt is only 1650!
    # Withheld caps at 1650!
    # Net wage = 3000 - 1650 = 1350 ₪
    net_wage_2, garnished_2, notice_2 = garnish_wages_for_loan(active_items, wage=3000.0, current_time=now)
    assert garnished_2 == 1650.0
    assert net_wage_2 == 1350.0
    assert active_items["loan_owed"] == 0.0
    assert active_items["is_defaulter"] is False  # Debt cleared!
    assert "Долг полностью погашен" in notice_2


# =============================================================================
# INTEGRATION & HANDLER CALLBACK TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_heist_join_callback_flow(isolated_test_db):
    db = isolated_test_db
    lobby_id = "test_cb_heist"
    lobby = HeistLobby(
        lobby_id=lobby_id,
        chat_id=123,
        initiator_id=9001,
        initiator_name="Капитан",
        board_id="b"
    )
    active_heist_lobbies[lobby_id] = lobby

    # User 9002 clicks Join
    cb = MagicMock()
    cb.data = f"heist_join:{lobby_id}"
    cb.from_user = MagicMock()
    cb.from_user.id = 9002
    cb.from_user.full_name = "Стрелок 9002"
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()

    await cb_heist_join(cb)
    cb.answer.assert_called_with("🦹 Ты вступил в банду налётчиков!", show_alert=False)
    assert 9002 in lobby.participants
    assert len(lobby.participants) == 2


@pytest.mark.asyncio
async def test_heist_start_callback_only_initiator(isolated_test_db):
    lobby_id = "test_start_heist"
    lobby = HeistLobby(
        lobby_id=lobby_id,
        chat_id=123,
        initiator_id=9001,
        initiator_name="Капитан",
        board_id="b"
    )
    lobby.participants = [9001, 9002]
    active_heist_lobbies[lobby_id] = lobby

    # Non-initiator clicks start -> rejected
    cb_intruder = MagicMock()
    cb_intruder.data = f"heist_start:{lobby_id}"
    cb_intruder.from_user.id = 9002
    cb_intruder.answer = AsyncMock()

    await cb_heist_start(cb_intruder)
    cb_intruder.answer.assert_called_with("Только главарь банды может дать команду на штурм!", show_alert=True)


@pytest.mark.asyncio
async def test_cmd_money_laundering_handler(isolated_test_db):
    db = isolated_test_db
    user_id = 9501
    await save_user_active_items(db, user_id, {"dirty_balance": 50_000.0}, "b")

    msg = MagicMock()
    msg.from_user.id = user_id
    msg.text = "/launder all"
    msg.reply = AsyncMock()

    await cmd_money_laundering(msg)
    msg.reply.assert_called_once()
    reply_text = msg.reply.call_args[0][0]
    assert "ТЕНЕВАЯ ПРАЧЕЧНАЯ АБУ" in reply_text
    assert "35,000 ₪ легли в карман чистыми" in reply_text


@pytest.mark.asyncio
async def test_cmd_start_heist_handler(isolated_test_db):
    db = isolated_test_db
    user_id = 9502

    msg = MagicMock()
    msg.from_user.id = user_id
    msg.from_user.full_name = "Анон Бандит"
    msg.chat.id = 777123
    msg.bot = MagicMock()
    sent_msg = MagicMock()
    sent_msg.message_id = 45678
    msg.reply = AsyncMock(return_value=sent_msg)

    await cmd_start_heist(msg)
    msg.reply.assert_called_once()
    reply_text = msg.reply.call_args[0][0]
    assert "НАЛЁТ НА ИНКАССАТОРСКИЙ БРОНЕВИК АБУ" in reply_text
    kb = msg.reply.call_args[1]["reply_markup"]
    assert "Вступить в банду (1/4)" in kb.inline_keyboard[0][0].text

    # Cancel timer task in lobby to prevent dangling task
    lid = chat_active_heist.get(777123)
    if lid and lid in active_heist_lobbies:
        lobby = active_heist_lobbies[lid]
        if lobby.timer_task:
            lobby.timer_task.cancel()


@pytest.mark.asyncio
async def test_cmd_loan_handler(isolated_test_db):
    db = isolated_test_db
    user_id = 9503

    msg = MagicMock()
    msg.from_user.id = user_id
    msg.text = "/loan 1000"
    msg.reply = AsyncMock()

    await cmd_loan(msg)
    msg.reply.assert_called_once()
    reply_text = msg.reply.call_args[0][0]
    assert "БЫСТРОШЕКЕЛЬ ПАХОМА" in reply_text
    assert "1,200 ₪" in reply_text


@pytest.mark.asyncio
async def test_cmd_paydebt_handler(isolated_test_db):
    db = isolated_test_db
    user_id = 9504

    # Borrow first
    await process_borrow_loan(db, user_id, 1000, board_id="b")
    # Add balance to repay
    await common.database.add_user_global_balance(db, user_id, "b", 500.0)

    msg = MagicMock()
    msg.from_user.id = user_id
    msg.text = "/paydebt"
    msg.reply = AsyncMock()

    await cmd_paydebt(msg)
    msg.reply.assert_called_once()
    reply_text = msg.reply.call_args[0][0]
    assert "ПАХОМ ДОВОЛЕН" in reply_text
    assert "1,200 ₪" in reply_text



# =============================================================================
# SYSTEM 4: PHRASE INTEGRATION, INTERACTIVE MENUS & MULTILINGUAL HELP TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_launder_washer_phrase_integration(isolated_test_db):
    """
    Verifies that money laundering confirmation incorporates a phrase from LAUNDER_WASHER_PHRASES.
    """
    db = isolated_test_db
    user_id = 7001
    board_id = "b"

    active_items = {"dirty_balance": 10_000.0}
    await save_user_active_items(db, user_id, active_items, board_id)

    success, msg, data = await process_money_laundering(db, user_id, "all", board_id=board_id)
    assert success is True
    assert "washer_flavor" in data
    assert data["washer_flavor"] in LAUNDER_WASHER_PHRASES
    assert data["washer_flavor"] in msg


@pytest.mark.asyncio
async def test_heist_battle_phrases_integration(isolated_test_db):
    """
    Verifies that heist battle resolutions pick random phrases from HEIST_WIN_PHRASES and HEIST_LOSE_PHRASES.
    """
    db = isolated_test_db
    board_id = "b"
    crew = [7002, 7003]
    for uid in crew:
        await save_user_active_items(db, uid, {}, board_id)
        await common.database.add_user_global_balance(db, uid, board_id, 5000.0)

    # 1. Victory phrase
    lid_win = "test_heist_win_phrase"
    lobby_win = HeistLobby(lid_win, 9091, crew[0], "Cap", board_id)
    lobby_win.participants = list(crew)
    for uid in crew:
        lobby_win.participant_names[uid] = f"Fighter {uid}"
    active_heist_lobbies[lid_win] = lobby_win

    res_win = await resolve_heist(lid_win, db=db, force_win=True)
    assert res_win["status"] == "won"
    assert "win_phrase" in res_win
    assert res_win["win_phrase"] in HEIST_WIN_PHRASES

    # 2. Defeat phrase
    lid_lose = "test_heist_lose_phrase"
    lobby_lose = HeistLobby(lid_lose, 9092, crew[0], "Cap", board_id)
    lobby_lose.participants = list(crew)
    for uid in crew:
        lobby_lose.participant_names[uid] = f"Fighter {uid}"
    active_heist_lobbies[lid_lose] = lobby_lose

    res_lose = await resolve_heist(lid_lose, db=db, force_win=False)
    assert res_lose["status"] == "lost"
    assert "lose_phrase" in res_lose
    assert res_lose["lose_phrase"] in HEIST_LOSE_PHRASES


def test_loan_collector_phrase_integration():
    """
    Verifies that overdue loan harassment text incorporates phrases from LOAN_PAKHOM_COLLECTOR_PHRASES.
    """
    now = time.time()
    active_items = {
        "loan_amount": 1000,
        "loan_owed": 1200,
        "loan_due_at": now - 3600,
        "is_defaulter": False
    }

    is_penalized, harassment_text = check_and_apply_loan_penalty(active_items, current_time=now)
    assert is_penalized is True
    assert any(phrase in harassment_text for phrase in LOAN_PAKHOM_COLLECTOR_PHRASES)


@pytest.mark.asyncio
async def test_cmd_launder_interactive_menu_and_callbacks(isolated_test_db):
    """
    Tests interactive laundering menu when /launder is called without args,
    as well as callbacks launder_hub, launder_do_all, and launder_do_half.
    """
    db = isolated_test_db
    user_id = 7004
    board_id = "b"

    # 1. No dirty balance -> rejection
    await save_user_active_items(db, user_id, {"dirty_balance": 0.0}, board_id)
    msg = MagicMock()
    msg.from_user.id = user_id
    msg.text = "/launder"
    msg.reply = AsyncMock()
    await cmd_money_laundering(msg)
    msg.reply.assert_called_once()
    assert "У тебя нет меченых шекелей" in msg.reply.call_args[0][0]

    # 2. Give 40,000 dirty balance -> shows menu card with buttons
    await save_user_active_items(db, user_id, {"dirty_balance": 40_000.0}, board_id)
    msg2 = MagicMock()
    msg2.from_user.id = user_id
    msg2.text = "/launder"
    msg2.reply = AsyncMock()
    await cmd_money_laundering(msg2)
    msg2.reply.assert_called_once()
    reply_text = msg2.reply.call_args[0][0]
    kb = msg2.reply.call_args[1]["reply_markup"]

    assert "ТЕНЕВАЯ ПРАЧЕЧНАЯ АБУ" in reply_text
    assert "40,000 ₪" in reply_text
    assert "30% налог" in reply_text
    assert len(kb.inline_keyboard) == 3
    assert kb.inline_keyboard[0][0].callback_data == "launder_do_all"
    assert kb.inline_keyboard[1][0].callback_data == "launder_do_half"
    assert kb.inline_keyboard[2][0].callback_data == "bank_main_hub"

    # 3. Test callback launder_hub
    cb_hub = MagicMock()
    cb_hub.from_user.id = user_id
    cb_hub.data = "launder_hub"
    cb_hub.answer = AsyncMock()
    cb_hub.message = MagicMock()
    cb_hub.message.edit_text = AsyncMock()
    await cb_launder_hub(cb_hub)
    cb_hub.answer.assert_called_once()
    cb_hub.message.edit_text.assert_called_once()

    # 4. Test callback launder_do_half (launder 20,000 out of 40,000)
    cb_half = MagicMock()
    cb_half.from_user.id = user_id
    cb_half.data = "launder_do_half"
    cb_half.answer = AsyncMock()
    cb_half.message = MagicMock()
    cb_half.message.edit_text = AsyncMock()
    await cb_launder_do_half(cb_half)
    cb_half.answer.assert_called_once()
    cb_half.message.edit_text.assert_called_once()

    items_after_half = await get_user_active_items(db, user_id, board_id)
    assert items_after_half["dirty_balance"] == 20_000.0
    bal_after_half = await common.database.get_user_global_balance(db, user_id)
    assert bal_after_half == 14_000.0  # 70% of 20,000

    # 5. Test callback launder_do_all (launder remaining 20,000)
    cb_all = MagicMock()
    cb_all.from_user.id = user_id
    cb_all.data = "launder_do_all"
    cb_all.answer = AsyncMock()
    cb_all.message = MagicMock()
    cb_all.message.edit_text = AsyncMock()
    await cb_launder_do_all(cb_all)
    cb_all.answer.assert_called_once()
    cb_all.message.edit_text.assert_called_once()

    items_after_all = await get_user_active_items(db, user_id, board_id)
    assert items_after_all["dirty_balance"] == 0.0
    bal_after_all = await common.database.get_user_global_balance(db, user_id)
    assert bal_after_all == 28_000.0  # 14,000 + 14,000


@pytest.mark.asyncio
async def test_cmd_loan_interactive_menu_and_callbacks(isolated_test_db):
    """
    Tests interactive loan menu when /loan is called without arguments,
    and handles callbacks for presets (500, 1000, 2500, 5000) and paydebt.
    """
    db = isolated_test_db
    user_id = 7005
    board_id = "b"

    # 1. /loan without args -> shows rich menu card
    await save_user_active_items(db, user_id, {"credit_rating": 120, "loan_owed": 0}, board_id)
    msg = MagicMock()
    msg.from_user.id = user_id
    msg.text = "/loan"
    msg.reply = AsyncMock()
    await cmd_loan(msg)
    msg.reply.assert_called_once()
    card_text = msg.reply.call_args[0][0]
    kb = msg.reply.call_args[1]["reply_markup"]

    assert "БЫСТРОШЕКЕЛЬ ПАХОМА" in card_text
    assert "Кредитный рейтинг:</b> 120" in card_text
    assert "Условия кредитования:" in card_text
    assert len(kb.inline_keyboard) == 4
    # Check buttons
    assert kb.inline_keyboard[0][0].callback_data == "loan_take_500"
    assert kb.inline_keyboard[0][1].callback_data == "loan_take_1000"
    assert kb.inline_keyboard[1][0].callback_data == "loan_take_2500"
    assert kb.inline_keyboard[1][1].callback_data == "loan_take_5000"
    assert kb.inline_keyboard[2][0].callback_data == "loan_paydebt_full"
    assert kb.inline_keyboard[3][0].callback_data == "work_hub"

    # 2. Test callback loan_hub
    cb_hub = MagicMock()
    cb_hub.from_user.id = user_id
    cb_hub.data = "loan_hub"
    cb_hub.answer = AsyncMock()
    cb_hub.message = MagicMock()
    cb_hub.message.edit_text = AsyncMock()
    await cb_loan_hub(cb_hub)
    cb_hub.answer.assert_called_once()
    cb_hub.message.edit_text.assert_called_once()

    # 3. Borrow 2,500 ₪ via callback loan_take_2500
    cb_take = MagicMock()
    cb_take.from_user.id = user_id
    cb_take.data = "loan_take_2500"
    cb_take.answer = AsyncMock()
    cb_take.message = MagicMock()
    cb_take.message.edit_text = AsyncMock()
    await cb_loan_take_preset(cb_take)
    cb_take.answer.assert_called_once()
    cb_take.message.edit_text.assert_called_once()

    # User now has 2,500 balance and owes 3,000 (2500 * 1.20)
    bal = await common.database.get_user_global_balance(db, user_id)
    assert bal == 2500.0
    items = await get_user_active_items(db, user_id, board_id)
    assert items["loan_owed"] == 3000
    assert items["loan_amount"] == 2500

    # 4. Attempting to take another loan via callback is rejected
    cb_take2 = MagicMock()
    cb_take2.from_user.id = user_id
    cb_take2.data = "loan_take_500"
    cb_take2.answer = AsyncMock()
    cb_take2.message = MagicMock()
    cb_take2.message.edit_text = AsyncMock()
    await cb_loan_take_preset(cb_take2)
    cb_take2.answer.assert_called_with("Ошибка оформления займа!", show_alert=True)

    # 5. Repay via callback loan_paydebt_full
    # Add 1,000 to user balance so balance is 3,500 >= 3,000
    await common.database.add_user_global_balance(db, user_id, board_id, 1000.0)
    cb_pay = MagicMock()
    cb_pay.from_user.id = user_id
    cb_pay.data = "loan_paydebt_full"
    cb_pay.answer = AsyncMock()
    cb_pay.message = MagicMock()
    cb_pay.message.edit_text = AsyncMock()
    await cb_loan_paydebt_full(cb_pay)
    cb_pay.answer.assert_called_with("🤝 Долг полностью погашен!", show_alert=False)

    items_repaid = await get_user_active_items(db, user_id, board_id)
    assert items_repaid["loan_owed"] == 0
    assert items_repaid["credit_rating"] == 130  # Increased rating +10


def test_help_sections_multilingual_crime_darknet_loan_heist():
    """
    Verifies that comprehensive documentation for /help crime, /help darknet,
    /help loan, /help heist exists across all three languages: RU, EN, and JP.
    """
    required_sections = ["crime", "darknet", "loan", "heist"]
    languages = ["ru", "en", "jp"]

    for sec in required_sections:
        for lang in languages:
            text = get_help_hub_page(sec, lang=lang)
            assert isinstance(text, str)
            assert len(text) > 100, f"Section {sec} in {lang} is too short!"

            # Balanced HTML tags
            for tag in ["b", "i", "code", "a"]:
                open_c = text.count(f"<{tag}>") + text.count(f"<{tag} ")
                close_c = text.count(f"</{tag}>")
                assert open_c == close_c, f"Unbalanced tag {tag} in {sec} ({lang})"


def test_help_darknet_items_descriptions():
    """
    Verifies that /help darknet covers all required darknet items:
    lockpicks, fake ksiva, 5g jammer, master key, bribe envelope, chloroform.
    """
    for lang in ["ru", "en", "jp"]:
        text = get_help_hub_page("darknet", lang=lang)

        # Check item identifiers
        assert "lockpick" in text
        assert "fake_ksiva" in text
        assert "jammer" in text
        assert "master_key" in text
        assert "bribe_envelope" in text
        assert "chloroform" in text

        # Check prices & mechanics mentioned
        assert "400" in text      # lockpick base
        assert "250" in text      # fake ksiva base
        assert "1,200" in text or "1200" in text  # jammer base
        assert "5,000" in text or "5000" in text  # master key base
        assert "2,500" in text or "2500" in text  # bribe envelope base
        assert "1,500" in text or "1500" in text  # chloroform base


def test_help_hub_page_aliases():
    """
    Verifies that get_help_hub_page maps aliases like 'налет', 'займ', 'heists', 'loans'.
    """
    # Russian aliases
    assert get_help_hub_page("налет", lang="ru") == get_help_hub_page("heist", lang="ru")
    assert get_help_hub_page("займ", lang="ru") == get_help_hub_page("loan", lang="ru")
    assert get_help_hub_page("даркнет", lang="ru") == get_help_hub_page("darknet", lang="ru")
    assert get_help_hub_page("криминал", lang="ru") == get_help_hub_page("crime", lang="ru")

    # English plural aliases
    assert get_help_hub_page("heists", lang="en") == get_help_hub_page("heist", lang="en")
    assert get_help_hub_page("loans", lang="en") == get_help_hub_page("loan", lang="en")


@pytest.mark.asyncio
async def test_launder_hub_from_photo_message_navigation(isolated_test_db):
    """
    Verifies that opening /launder from a photo banner (such as Bank Hub)
    deletes the photo banner and sends clean text menu with buttons.
    """
    db = isolated_test_db
    user_id = 8801
    await save_user_active_items(db, user_id, {"dirty_balance": 50_000.0}, "b")

    cb = MagicMock()
    cb.from_user.id = user_id
    cb.data = "launder_hub"
    cb.answer = AsyncMock()
    msg = MagicMock()
    msg.photo = [MagicMock()]
    msg.delete = AsyncMock()
    msg.answer = AsyncMock()
    cb.message = msg

    with patch("common.db_pool.get_pool", AsyncMock(return_value=db)):
        await cb_launder_hub(cb)

    msg.delete.assert_called_once()
    msg.answer.assert_called_once()
    sent_text = msg.answer.call_args[0][0] if msg.answer.call_args[0] else msg.answer.call_args[1].get('text', '')
    assert "ТЕНЕВАЯ ПРАЧЕЧНАЯ АБУ" in sent_text
    cb.answer.assert_called_once()


@pytest.mark.asyncio
async def test_loan_hub_and_preset_from_photo_message_navigation(isolated_test_db):
    """
    Verifies that opening /loan or borrowing from a photo banner (such as Work Hub)
    deletes the photo banner and sends clean text menu, without throwing TelegramBadRequest.
    """
    db = isolated_test_db
    user_id = 8802
    await save_user_active_items(db, user_id, {"credit_rating": 100, "loan_owed": 0}, "b")

    # 1. Open loan hub from photo banner
    cb = MagicMock()
    cb.from_user.id = user_id
    cb.data = "loan_hub"
    cb.answer = AsyncMock()
    msg = MagicMock()
    msg.photo = [MagicMock()]
    msg.delete = AsyncMock()
    msg.answer = AsyncMock()
    cb.message = msg

    with patch("common.db_pool.get_pool", AsyncMock(return_value=db)):
        await cb_loan_hub(cb)

    msg.delete.assert_called_once()
    msg.answer.assert_called_once()
    sent_text = msg.answer.call_args[0][0] if msg.answer.call_args[0] else msg.answer.call_args[1].get('text', '')
    assert "БЫСТРОШЕКЕЛЬ ПАХОМА" in sent_text
    cb.answer.assert_called_once()

    # 2. Take loan preset from photo banner
    cb_take = MagicMock()
    cb_take.from_user.id = user_id
    cb_take.data = "loan_take_500"
    cb_take.answer = AsyncMock()
    msg_take = MagicMock()
    msg_take.photo = [MagicMock()]
    msg_take.delete = AsyncMock()
    msg_take.answer = AsyncMock()
    cb_take.message = msg_take

    with patch("common.db_pool.get_pool", AsyncMock(return_value=db)):
        await cb_loan_take_preset(cb_take)

    msg_take.delete.assert_called_once()
    msg_take.answer.assert_called_once()
    cb_take.answer.assert_called_with("🪙 Займ 500 ₪ оформлен!", show_alert=False)
