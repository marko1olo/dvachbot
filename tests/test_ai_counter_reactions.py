# -*- coding: utf-8 -*-
"""
tests/test_ai_counter_reactions.py
==================================
Comprehensive test suite verifying Requirement R4:
Hilarious & Brutal Counter-Reactions on AI Target Attacks (author_id == 0).
- /shoot -> 15m ricochet mute
- /rob -> 500 ₪ fine to Abu Fund
- /shit -> 1h self-debuff
- /vomit -> 1h self-debuff
- /pepperspray -> 30m blindness
- /partyvan -> 2h arrest for false reporting
- /dossier -> Alpha-Tier gigachad stats
- /bribe -> rejection & burning
"""

import pytest
import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

from common.bot_helpers import handle_cyberchad_counter_action, _get_user_active_items
from common.database import get_user_global_balance, get_abu_fund_total


@pytest.mark.asyncio
async def test_cyberchad_counter_shoot(isolated_test_db):
    """Verifies that /shoot against Cyberchad causes a 15-minute mute backfire."""
    db = isolated_test_db
    user_id = 12345
    board_id = "b"

    mock_msg = MagicMock()
    mock_msg.answer = AsyncMock()

    handled = await handle_cyberchad_counter_action(mock_msg, "shoot", user_id, board_id, db)
    assert handled is True

    # Verify message response
    assert mock_msg.answer.called
    ans_text = mock_msg.answer.call_args[0][0]
    assert "РИКОШЕТ МУТ-ГАНА" in ans_text
    assert "15 минут" in ans_text

    # Verify combat log transaction
    async with db.execute("SELECT amount, category, description FROM UserTransactions WHERE user_id = ?", (user_id,)) as c:
        row = await c.fetchone()
        assert row is not None
        assert row[1] == "combat"
        assert "Рикошет Мут-Гана" in row[2]


@pytest.mark.asyncio
async def test_cyberchad_counter_rob(isolated_test_db):
    """Verifies that /rob against Cyberchad fines the user 500 ₪ into Abu Fund."""
    db = isolated_test_db
    user_id = 23456
    board_id = "b"

    # Seed user balance
    from common.database import add_user_global_balance
    await add_user_global_balance(db, user_id, board_id, 1500)

    initial_abu = await get_abu_fund_total(db)

    mock_msg = MagicMock()
    mock_msg.answer = AsyncMock()

    handled = await handle_cyberchad_counter_action(mock_msg, "rob", user_id, board_id, db)
    assert handled is True

    # Verify message response
    assert mock_msg.answer.called
    ans_text = mock_msg.answer.call_args[0][0]
    assert "ОГРАБЛЕНИЕ ПРОВАЛЕНО" in ans_text
    assert "-500" in ans_text

    # Verify user balance deducted by 500
    new_bal = await get_user_global_balance(db, user_id)
    assert new_bal == 1000

    # Verify Abu Fund credited by 500
    new_abu = await get_abu_fund_total(db)
    assert new_abu == initial_abu + 500


@pytest.mark.asyncio
async def test_cyberchad_counter_shit(isolated_test_db):
    """Verifies that /shit against Cyberchad inflicts 1-hour self-debuff."""
    db = isolated_test_db
    user_id = 34567
    board_id = "b"

    mock_msg = MagicMock()
    mock_msg.answer = AsyncMock()

    handled = await handle_cyberchad_counter_action(mock_msg, "shit", user_id, board_id, db)
    assert handled is True

    # Verify message response
    assert mock_msg.answer.called
    ans_text = mock_msg.answer.call_args[0][0]
    assert "КРИТИЧЕСКИЙ САМООБСЁР" in ans_text
    assert "1 час" in ans_text

    # Verify active_items in DB has shit_until set in future
    u_items = await _get_user_active_items(db, user_id, board_id)
    assert u_items.get("shit_until", 0) > int(time.time()) + 3500


@pytest.mark.asyncio
async def test_cyberchad_counter_vomit(isolated_test_db):
    """Verifies that /vomit against Cyberchad inflicts 1-hour self-debuff."""
    db = isolated_test_db
    user_id = 45678
    board_id = "b"

    mock_msg = MagicMock()
    mock_msg.answer = AsyncMock()

    handled = await handle_cyberchad_counter_action(mock_msg, "vomit", user_id, board_id, db)
    assert handled is True

    # Verify message response
    assert mock_msg.answer.called
    ans_text = mock_msg.answer.call_args[0][0]
    assert "ОБРАТНЫЙ РЕФЛЮКС" in ans_text
    assert "1 час" in ans_text

    # Verify active_items in DB has vomit_until set in future
    u_items = await _get_user_active_items(db, user_id, board_id)
    assert u_items.get("vomit_until", 0) > int(time.time()) + 3500


@pytest.mark.asyncio
async def test_cyberchad_counter_pepperspray(isolated_test_db):
    """Verifies that /pepperspray against Cyberchad blinds the user for 30 minutes."""
    db = isolated_test_db
    user_id = 56789
    board_id = "b"

    mock_msg = MagicMock()
    mock_msg.answer = AsyncMock()

    handled = await handle_cyberchad_counter_action(mock_msg, "pepperspray", user_id, board_id, db)
    assert handled is True

    # Verify message response
    assert mock_msg.answer.called
    ans_text = mock_msg.answer.call_args[0][0]
    assert "ПЕРЦОВЫЙ ИНГАЛЯТОР" in ans_text
    assert "30 минут" in ans_text

    # Verify active_items in DB has peppersprayed_until set in future
    u_items = await _get_user_active_items(db, user_id, board_id)
    assert u_items.get("peppersprayed_until", 0) > int(time.time()) + 1700


@pytest.mark.asyncio
async def test_cyberchad_counter_partyvan(isolated_test_db):
    """Verifies that /partyvan against Cyberchad arrests the false reporter for 2 hours."""
    db = isolated_test_db
    user_id = 67890
    board_id = "b"

    mock_msg = MagicMock()
    mock_msg.answer = AsyncMock()

    handled = await handle_cyberchad_counter_action(mock_msg, "partyvan", user_id, board_id, db)
    assert handled is True

    # Verify message response
    assert mock_msg.answer.called
    ans_text = mock_msg.answer.call_args[0][0]
    assert "ЛОЖНЫЙ ДОНОС НА КИБЕРЧЕДА" in ans_text
    assert "2 часа" in ans_text

    # Verify combat log transaction
    async with db.execute("SELECT category, description FROM UserTransactions WHERE user_id = ?", (user_id,)) as c:
        row = await c.fetchone()
        assert row is not None
        assert row[0] == "combat"
        assert "Арест за ложный донос на Киберчеда (2ч)" in row[1]


@pytest.mark.asyncio
async def test_cyberchad_counter_bribe(isolated_test_db):
    """Verifies that /bribe against Cyberchad is rejected and incinerated."""
    db = isolated_test_db
    user_id = 78901
    board_id = "b"

    mock_msg = MagicMock()
    mock_msg.answer = AsyncMock()

    handled = await handle_cyberchad_counter_action(mock_msg, "bribe", user_id, board_id, db)
    assert handled is True

    assert mock_msg.answer.called
    ans_text = mock_msg.answer.call_args[0][0]
    assert "ВЗЯТКА НЕ ПРИНЯТА" in ans_text
    assert "Киберчед" in ans_text


@pytest.mark.asyncio
async def test_cyberchad_counter_dossier(isolated_test_db):
    """Verifies that /dossier against Cyberchad returns Alpha-Tier gigachad stats."""
    db = isolated_test_db
    user_id = 89012
    board_id = "b"

    mock_msg = MagicMock()
    mock_msg.answer = AsyncMock()

    handled = await handle_cyberchad_counter_action(mock_msg, "dossier", user_id, board_id, db)
    assert handled is True

    assert mock_msg.answer.called
    ans_text = mock_msg.answer.call_args[0][0]
    assert "ДОСЬЕ НА КИБЕРЧЕДА" in ans_text
    assert "КИБЕРЧЕД-9000" in ans_text
    assert "Alpha-Tier" in ans_text
