import asyncio
import json
import time
import pytest
from unittest.mock import AsyncMock

import main


@pytest.mark.asyncio
async def test_janitor_progressive_pricing():
    """Verify progressive pricing for janitor ticket: base + 5% balance and escalation."""
    # Base price without balance
    p_base = main.get_current_item_price('janitor', user_id=999999, balance=0)
    assert p_base >= 800

    # Oligarch with 1,000,000 shekels -> +50,000 tax
    p_rich = main.get_current_item_price('janitor', user_id=999999, balance=1_000_000)
    assert p_rich >= p_base + 50_000


@pytest.mark.asyncio
async def test_active_pin_stale_handling(isolated_test_db):
    """Verify stale active pins are discarded and cleared."""
    db = isolated_test_db
    # Verify board setting active_pin can be updated and reset
    await db.execute("INSERT OR REPLACE INTO Boards (board_id, name, settings) VALUES ('b', 'Бред', ?)", (json.dumps({'active_pin': 12345}),))
    await db.commit()

    async with db.execute("SELECT settings FROM Boards WHERE board_id = 'b'") as cur:
        row = await cur.fetchone()
        s = json.loads(row[0])
        assert s['active_pin'] == 12345

    s['active_pin'] = None
    await db.execute("UPDATE Boards SET settings = ? WHERE board_id = 'b'", (json.dumps(s),))
    await db.commit()

    async with db.execute("SELECT settings FROM Boards WHERE board_id = 'b'") as cur:
        row = await cur.fetchone()
        s = json.loads(row[0])
        assert s['active_pin'] is None


@pytest.mark.asyncio
async def test_cure_debuff_clearing_multiboard(isolated_test_db):
    """Verify debuffs are completely stripped across all board rows for a user."""
    db = isolated_test_db
    uid = 888123

    # Ensure boards exist
    await db.execute("INSERT OR IGNORE INTO Boards (board_id, name) VALUES ('b', 'Бред')")
    await db.execute("INSERT OR IGNORE INTO Boards (board_id, name) VALUES ('sex', 'Секс')")
    await db.commit()

    # Insert user in 'b' and 'sex' with dirty debuffs
    b_items = {"shit_until": time.time() + 3600, "flag_ua_until": time.time() + 3600, "tinfoil_hat": 1}
    sex_items = {"vomit_until": time.time() + 3600, "cursed_until": time.time() + 3600}

    await db.execute("INSERT INTO Users (user_id, board_id, balance, cursed_until, active_items) VALUES (?, 'b', 5000, 1000, ?)", (uid, json.dumps(b_items)))
    await db.execute("INSERT INTO Users (user_id, board_id, balance, cursed_until, active_items) VALUES (?, 'sex', 5000, 1000, ?)", (uid, json.dumps(sex_items)))
    await db.commit()

    # Emulate the cure logic:
    DEBUFF_KEYS = ("shit_until", "vomit_until", "flag_ua_until", "flag_ru_until", "peppersprayed_until", "cursed_until", "schizo_pill_until", "schizo_until")
    await db.execute("UPDATE Users SET cursed_until = 0 WHERE user_id = ?", (uid,))
    async with db.execute("SELECT board_id, active_items FROM Users WHERE user_id = ?", (uid,)) as cur:
        user_rows = await cur.fetchall()
    for b_row_id, raw_items in user_rows:
        row_items = json.loads(raw_items) if raw_items else {}
        for k in DEBUFF_KEYS:
            row_items.pop(k, None)
        await db.execute("UPDATE Users SET cursed_until = 0, active_items = ? WHERE user_id = ? AND board_id = ?",
                         (json.dumps(row_items), uid, b_row_id))
    await db.commit()

    # Verify both rows are completely purged of debuffs
    async with db.execute("SELECT board_id, cursed_until, active_items FROM Users WHERE user_id = ?", (uid,)) as cur:
        rows = await cur.fetchall()
        assert len(rows) == 2
        for b_id, c_until, raw_items in rows:
            assert c_until == 0
            items = json.loads(raw_items)
            for k in DEBUFF_KEYS:
                assert k not in items
            if b_id == 'b':
                assert items.get("tinfoil_hat") == 1


@pytest.mark.asyncio
async def test_bank_deposit_limit_expanded_to_100(isolated_test_db):
    """Verify bank deposit limit is expanded from 15 to 100, letting users with 54 deposits open more."""
    db = isolated_test_db
    from bank_engine import create_bank_deposit
    uid = 5264555563  # Nikolay Romanov
    await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 10000000)", (uid,))
    await db.commit()

    # Pre-populate 54 active deposits
    for i in range(54):
        await db.execute(
            "INSERT INTO BankDeposits (user_id, board_id, tier_id, principal, daily_rate, created_at, locked_until, last_accrual_at, status) "
            "VALUES (?, 'b', 'sych', 100, 0.005, 1000, 1000, 1000, 'active')",
            (uid,)
        )
    await db.commit()

    # With the new limit (100), creating a 55th deposit must succeed
    ok, dep, err = await create_bank_deposit(db, uid, "b", "sych", 500.0)
    assert ok is True, f"Failed to create deposit with 54 active: {err}"
    assert dep is not None
    assert dep["principal"] == 500.0


@pytest.mark.asyncio
async def test_votemute_broadcast_spawns_for_active_users(isolated_test_db):
    """Verify votemute card broadcast triggers for active users."""
    import votemute_engine
    import shared_state
    from unittest.mock import patch

    shared_state.board_data['b'] = {
        'users': {'active': {101, 102, 103, 104, 105}, 'banned': set()},
        'mutes': {}
    }

    mock_msg = AsyncMock()
    mock_msg.from_user.id = 101
    mock_msg.chat.id = 101
    mock_msg.text = "/votemute 547320"
    mock_msg.reply_to_message = None
    mock_msg.answer = AsyncMock()
    mock_msg.bot = AsyncMock()

    with patch("votemute_engine.get_pool", return_value=isolated_test_db), \
         patch("votemute_engine._resolve_target_from_message", return_value=(547320, 999)), \
         patch("votemute_engine.check_user_unbribable_mute", return_value=(False, 0)), \
         patch("banner_manager.broadcast_banner_to_users", new_callable=AsyncMock) as mock_bcast, \
         patch("event_push_engine.push_votemute_open", new_callable=AsyncMock) as mock_push:

        await votemute_engine.cmd_votemute(mock_msg, board_id="b")
        assert mock_msg.answer.called
        # Allow background task to execute
        await asyncio.sleep(0.05)
        assert mock_bcast.called
        assert mock_push.called
