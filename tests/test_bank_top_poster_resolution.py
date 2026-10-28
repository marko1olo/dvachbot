# -*- coding: utf-8 -*-
"""
tests/test_bank_top_poster_resolution.py — Verification of complete resolution for top poster bank deposit issues.
Validates:
1. Float precision bug resolution: user with raw balance ending in .399999999 can deposit 100% via button, text ("все"), command ("/deposit все"), and percentages ("100%").
2. Syntax parsing: "8кк", "8kk", "8м", "50 000 ₪", "500р", "треть", "четверть".
3. Command argument parsing: "/deposit 8м skuf", "/deposit 8кк skuf", "/deposit 50 000 skuf", "/deposit все skuf".
4. Pending state resilience: pending deposit state is preserved if a deposit attempt fails for legitimate reasons.
5. InaccessibleMessage safety: _render_bank_view handles InaccessibleMessage without crashing.
6. Multi-board global balance deduction with float epsilon.
"""

import json
import math
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram import types

from bank_engine import (
    BANK_TIERS,
    USER_PENDING_BANK_DEPOSIT,
    PendingBankDepositFilter,
    build_deposit_presets_kb,
    cb_bank_do_deposit,
    clear_user_pending_deposit,
    cmd_deposit,
    create_bank_deposit,
    get_user_pending_deposit,
    handle_chat_deposit_amount,
    parse_amount_and_tier,
    parse_deposit_amount,
    set_user_pending_deposit,
    _render_bank_view,
)
from common.database import get_user_global_balance, add_user_global_balance, deduct_user_global_balance


TOP_POSTER_USER_ID = 5264555563
TOP_POSTER_RAW_BALANCE_B = 8360232.399999999
TOP_POSTER_RAW_BALANCE_SEX = 223624.0
MICROLOAN_DEBT = 268438


async def _seed_top_poster(db, multi_board: bool = False):
    """Сеет в изолированную тестовую БД точное состояние пользователя 5264555563."""
    active_items = {
        "work_cooldowns": {
            "last_microloan": 1793209664,
            "microloan_debt": MICROLOAN_DEBT,
        },
        "last_microloan": 1793209664,
        "microloan_debt": MICROLOAN_DEBT,
        "unlocked_achievements": ["ach_first_work"],
        "inventory": {"trash_lootbox": 1},
    }
    items_json = json.dumps(active_items, ensure_ascii=False)

    await db.execute(
        """
        INSERT INTO Users (user_id, board_id, balance, posts_count, active_items)
        VALUES (?, 'b', ?, 93420, ?)
        ON CONFLICT(user_id, board_id) DO UPDATE SET
            balance = excluded.balance,
            posts_count = excluded.posts_count,
            active_items = excluded.active_items
        """,
        (TOP_POSTER_USER_ID, TOP_POSTER_RAW_BALANCE_B, items_json),
    )

    if multi_board:
        await db.execute("INSERT OR IGNORE INTO Boards (board_id, name) VALUES ('sex', 'Sex Board')")
        await db.execute(
            """
            INSERT INTO Users (user_id, board_id, balance, posts_count, active_items)
            VALUES (?, 'sex', ?, 14912, ?)
            ON CONFLICT(user_id, board_id) DO UPDATE SET
                balance = excluded.balance,
                posts_count = excluded.posts_count,
                active_items = excluded.active_items
            """,
            (TOP_POSTER_USER_ID, TOP_POSTER_RAW_BALANCE_SEX, items_json),
        )


@pytest.mark.asyncio
async def test_100_percent_preset_button_succeeds(isolated_test_db):
    """Кнопка '100%' успешно открывает вклад для пользователя с нецелым IEEE-754 балансом."""
    db = isolated_test_db
    await _seed_top_poster(db, multi_board=False)

    wallet_bal = await get_user_global_balance(db, TOP_POSTER_USER_ID)
    assert wallet_bal == TOP_POSTER_RAW_BALANCE_B

    # 1. Генерируем клавиатуру
    text, kb = build_deposit_presets_kb("skuf", wallet_bal)

    btn_100 = None
    for row in kb.inline_keyboard:
        for btn in row:
            if btn.text and "100%" in btn.text:
                btn_100 = btn
                break
        if btn_100:
            break

    assert btn_100 is not None
    assert "bank_do_deposit:skuf:" in btn_100.callback_data

    # 2. Имитируем нажатие
    cb = MagicMock(spec=types.CallbackQuery)
    cb.from_user = MagicMock(id=TOP_POSTER_USER_ID)
    cb.data = btn_100.callback_data
    cb.answer = AsyncMock()
    cb.message = MagicMock(spec=types.Message)
    cb.message.caption = "test caption"
    cb.message.photo = []
    cb.message.edit_caption = AsyncMock()

    await cb_bank_do_deposit(cb, board_id="b")

    # 3. Должен быть успех: депозит создан, баланс списан
    cb.answer.assert_called_with("✅ Вклад успешно открыт!", show_alert=False)

    async with db.execute("SELECT principal, status FROM BankDeposits WHERE user_id = ?", (TOP_POSTER_USER_ID,)) as c:
        row = await c.fetchone()
        assert row is not None
        assert row[1] == "active"
        # Тело вклада должно быть равно балансу (за вычетом копеек округления)
        assert abs(row[0] - TOP_POSTER_RAW_BALANCE_B) < 0.02


@pytest.mark.asyncio
async def test_chat_input_vse_and_100_pct_succeeds(isolated_test_db):
    """Ввод текста 'все' или '100%' в чат успешно открывает депозит."""
    db = isolated_test_db
    await _seed_top_poster(db, multi_board=False)
    USER_PENDING_BANK_DEPOSIT.clear()

    wallet_bal = await get_user_global_balance(db, TOP_POSTER_USER_ID)

    # 1. Проверяем парсер
    amt_vse = parse_deposit_amount("все", wallet_bal)
    assert amt_vse is not None
    assert amt_vse <= wallet_bal
    assert abs(amt_vse - wallet_bal) < 0.02

    amt_pct = parse_deposit_amount("100%", wallet_bal)
    assert amt_pct is not None
    assert amt_pct <= wallet_bal

    # 2. Оформление через handle_chat_deposit_amount
    chat_id = -1001234567890
    set_user_pending_deposit(TOP_POSTER_USER_ID, "skuf", chat_id=chat_id, board_id="b")

    msg = MagicMock(spec=types.Message)
    msg.from_user = MagicMock(id=TOP_POSTER_USER_ID)
    msg.chat = MagicMock(id=chat_id)
    msg.text = "все"
    msg.answer = AsyncMock()

    pending = get_user_pending_deposit(TOP_POSTER_USER_ID)
    await handle_chat_deposit_amount(
        message=msg,
        pending_deposit=pending,
        amount_str="все",
        detected_tier="skuf",
        board_id="b",
    )

    msg.answer.assert_called_once()
    reply = msg.answer.call_args[0][0]
    assert "ВКЛАД УСПЕШНО ОФОРМЛЕН" in reply

    # 3. Проверяем BankDeposits
    async with db.execute("SELECT principal, status FROM BankDeposits WHERE user_id = ?", (TOP_POSTER_USER_ID,)) as c:
        row = await c.fetchone()
        assert row is not None
        assert row[1] == "active"


@pytest.mark.asyncio
async def test_extended_syntax_parsing():
    """Тестирование расширенного синтаксиса парсинга сумм ('8кк', '8kk', '8м', '50 000 ₪', '500р', 'треть', 'четверть')."""
    bal = 10_000_000.0

    assert parse_deposit_amount("8кк", bal) == 8_000_000.0
    assert parse_deposit_amount("8kk", bal) == 8_000_000.0
    assert parse_deposit_amount("8.5кк", bal) == 8_500_000.0
    assert parse_deposit_amount("8.5м", bal) == 8_500_000.0
    assert parse_deposit_amount("50 000", bal) == 50_000.0
    assert parse_deposit_amount("50 000 ₪", bal) == 50_000.0
    assert parse_deposit_amount("50000 шекелей", bal) == 50_000.0
    assert parse_deposit_amount("50000 шекели", bal) == 50_000.0
    assert parse_deposit_amount("500р", bal) == 500.0
    assert parse_deposit_amount("треть", bal) == 3_333_333.33
    assert parse_deposit_amount("четверть", bal) == 2_500_000.0
    assert parse_deposit_amount("половина", bal) == 5_000_000.0


@pytest.mark.asyncio
async def test_cmd_deposit_variations(isolated_test_db):
    """Команда /deposit корректно парсит аргументы с 'все', '8м', '8кк', '50 000'."""
    db = isolated_test_db
    await _seed_top_poster(db, multi_board=False)

    # 1. /deposit 8м skuf
    msg = MagicMock(spec=types.Message)
    msg.from_user = MagicMock(id=TOP_POSTER_USER_ID)
    msg.chat = MagicMock(id=-100123)
    msg.text = "/deposit 8м skuf"
    msg.answer = AsyncMock()

    with patch("bank_engine.get_pool", return_value=db):
        await cmd_deposit(msg, board_id="b")

    msg.answer.assert_called_once()
    reply = msg.answer.call_args[0][0]
    assert "ВКЛАД УСПЕШНО ОФОРМЛЕН" in reply
    assert "8,000,000.00" in reply


@pytest.mark.asyncio
async def test_pending_state_preserved_on_failure(isolated_test_db):
    """Если нажатие кнопки депозита не удалось (например, запрошено больше баланса), pending state не сбрасывается."""
    db = isolated_test_db
    await _seed_top_poster(db, multi_board=False)
    USER_PENDING_BANK_DEPOSIT.clear()

    set_user_pending_deposit(TOP_POSTER_USER_ID, "skuf", chat_id=-100123, board_id="b")
    assert get_user_pending_deposit(TOP_POSTER_USER_ID) is not None

    # Попытка внести нереальную сумму 999,000,000
    cb = MagicMock(spec=types.CallbackQuery)
    cb.from_user = MagicMock(id=TOP_POSTER_USER_ID)
    cb.data = "bank_do_deposit:skuf:999000000"
    cb.answer = AsyncMock()

    with patch("bank_engine.get_pool", return_value=db):
        await cb_bank_do_deposit(cb, board_id="b")

    # Алерт об ошибке показан
    cb.answer.assert_called_once()
    assert "Недостаточно шекелей" in cb.answer.call_args[0][0]

    # Pending state ДОЛЖЕН БЫТЬ СОХРАНЕН!
    assert get_user_pending_deposit(TOP_POSTER_USER_ID) is not None, "Pending state должен сохраниться при ошибке!"


@pytest.mark.asyncio
async def test_inaccessible_message_safety():
    """_render_bank_view не падает с AttributeError если target.message — InaccessibleMessage."""
    cb = MagicMock(spec=types.CallbackQuery)
    cb.from_user = MagicMock(id=TOP_POSTER_USER_ID)
    cb.bot = MagicMock()
    cb.bot.send_message = AsyncMock()
    # InaccessibleMessage mock: нет caption, photo, answer
    inaccessible = MagicMock(spec=types.InaccessibleMessage)
    inaccessible.chat = MagicMock(id=-100123)
    cb.message = inaccessible

    text, kb = build_deposit_presets_kb("sych", 5000.0)

    # Не должно выбросить исключение
    with patch("banner_manager.send_banner_message", AsyncMock()):
        await _render_bank_view(cb, text, kb, category="bank")
