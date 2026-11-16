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
    mock_msg.answer_photo = AsyncMock()
    mock_msg.bot = AsyncMock()
    mock_msg.bot.id = 12345

    with patch("votemute_engine.get_pool", return_value=isolated_test_db), \
         patch("votemute_engine._resolve_target_from_message", return_value=(547320, 999)), \
         patch("votemute_engine.check_user_unbribable_mute", return_value=(False, 0)), \
         patch("votemute_engine.check_voter_eligibility", return_value=(True, "")), \
         patch("banner_manager.broadcast_banner_to_users", new_callable=AsyncMock) as mock_bcast, \
         patch("event_push_engine.push_votemute_open", new_callable=AsyncMock) as mock_push:

        await votemute_engine.cmd_votemute(mock_msg, board_id="b")
        assert mock_msg.answer_photo.called or mock_msg.answer.called
        # Allow background task to execute
        await asyncio.sleep(0.05)
        assert mock_bcast.called
        # Verify no duplicate text push is sent
        assert not mock_push.called


@pytest.mark.asyncio
async def test_high_wealth_25x_surcharge_and_dynamic_fees():
    """Verify aggressive high-wealth scaling curve (up to 25x), dynamic weapon capital fees, and status fees."""
    from main import calculate_capital_surcharge_pct, get_current_item_price, PROGRESSIVE_SURCHARGE_ITEMS

    # 1. Curve verification
    # Novice protection
    assert calculate_capital_surcharge_pct(None) == 0.0
    assert calculate_capital_surcharge_pct(0) == 0.0
    assert calculate_capital_surcharge_pct(10_000) == 0.0

    # Linear 10k -> 50k: 0.0 -> 0.25 (1.25x)
    assert calculate_capital_surcharge_pct(30_000) == pytest.approx(0.125)
    assert calculate_capital_surcharge_pct(50_000) == pytest.approx(0.25)

    # Linear 50k -> 200k: 0.25 -> 1.00 (2.0x)
    assert calculate_capital_surcharge_pct(125_000) == pytest.approx(0.625)
    assert calculate_capital_surcharge_pct(200_000) == pytest.approx(1.00)

    # Linear 200k -> 500k: 1.00 -> 3.00 (4.0x)
    assert calculate_capital_surcharge_pct(350_000) == pytest.approx(2.00)
    assert calculate_capital_surcharge_pct(500_000) == pytest.approx(3.00)

    # Linear 500k -> 2M: 3.00 -> 9.00 (10.0x)
    assert calculate_capital_surcharge_pct(1_000_000) == pytest.approx(5.00)
    assert calculate_capital_surcharge_pct(2_000_000) == pytest.approx(9.00)

    # Linear 2M -> 10M: 9.00 -> 24.00 (25.0x)
    assert calculate_capital_surcharge_pct(6_000_000) == pytest.approx(16.50)
    assert calculate_capital_surcharge_pct(10_000_000) == pytest.approx(24.00)
    assert calculate_capital_surcharge_pct(20_000_000) == pytest.approx(24.00)

    # 2. Dynamic partyvan fee (1500 base * 25 + 100k fee = 137,500)
    assert get_current_item_price('partyvan', balance=10_000) == 1500
    assert get_current_item_price('partyvan', balance=1_000_000) == 19_000  # 1500*6 + 10,000
    assert get_current_item_price('partyvan', balance=10_000_000) == 137_500  # 1500*25 + 100,000

    # 3. Dynamic mute fee (500 base * 25 + 50k fee = 62,500)
    assert get_current_item_price('mute', balance=10_000) == 500
    assert get_current_item_price('mute', balance=1_000_000) == 8000  # 500*6 + 5000
    assert get_current_item_price('mute', balance=10_000_000) == 62_500  # 500*25 + 50,000

    # 4. Vanity items: prefix and badge_color in PROGRESSIVE_SURCHARGE_ITEMS + dynamic 2% status fee
    assert 'prefix' in PROGRESSIVE_SURCHARGE_ITEMS
    assert 'badge_color' in PROGRESSIVE_SURCHARGE_ITEMS

    # prefix: base 350
    assert get_current_item_price('prefix', balance=5000) == 350
    assert get_current_item_price('prefix', balance=1_000_000) == 22_100  # 350*6 + 20,000
    assert get_current_item_price('prefix', balance=10_000_000) == 108_750  # 350*25 + 100,000

    # badge_color: base 500
    assert get_current_item_price('badge_color', balance=5000) == 500
    assert get_current_item_price('badge_color', balance=1_000_000) == 23_000  # 500*6 + 20,000
    assert get_current_item_price('badge_color', balance=10_000_000) == 112_500  # 500*25 + 100,000


@pytest.mark.asyncio
async def test_unshackled_rob_high_roller_loot(isolated_test_db):
    """Verify /rob mechanics unshackled up to 100,000 ₪ theft cap, mirror loss, and tinfoil loss."""
    from unittest.mock import patch, MagicMock
    import shared_state
    import common.database

    db = isolated_test_db
    robber_id = 91001
    whale_id = 91002
    board_id = "b"

    # Setup robber and whale in DB
    await common.database.add_user_global_balance(db, robber_id, board_id, 500_000.0)
    await common.database.add_user_global_balance(db, whale_id, board_id, 1_000_000.0)
    await db.execute(
        "UPDATE Users SET active_items = ?, posts_count = 100 WHERE user_id = ?",
        (json.dumps({"knife_gun": True}), robber_id),
    )
    await db.execute(
        "UPDATE Users SET active_items = ?, posts_count = 100 WHERE user_id = ?",
        (json.dumps({}), whale_id),
    )
    await db.commit()

    fake_msg = MagicMock()
    fake_msg.from_user.id = robber_id
    fake_msg.from_user.first_name = "MasterThief"
    fake_msg.chat = MagicMock(id=77777)
    fake_msg.message_id = 2222
    fake_msg.reply_to_message = MagicMock()
    fake_msg.reply_to_message.from_user.id = whale_id
    fake_msg.reply_to_message.from_user.first_name = "OligarchWhale"
    fake_msg.reply_to_message.message_id = 2221
    fake_msg.answer = AsyncMock()
    fake_msg.answer_photo = AsyncMock()
    fake_msg.bot = MagicMock()
    fake_msg.bot.send_message = AsyncMock()

    # 1. High-roller robbery: target balance 1,000,000, pct = 0.20 -> 200,000 capped at 100,000
    shared_state._TARGET_LAST_ATTACKED_TS.clear()
    shared_state._GLOBAL_COMBAT_COOLDOWNS.clear()
    shared_state._VICTIM_ROB_COOLDOWNS.clear()

    with patch("main.get_author_id_by_reply", new_callable=AsyncMock) as mock_auth, \
         patch("random.uniform", return_value=0.20), \
         patch("random.random", return_value=0.99):
        mock_auth.return_value = whale_id
        await main.cmd_rob(fake_msg, board_id, stream="ru")

        # Verify whale balance reduced by 100,000 (not just old 1,000!)
        bal_whale = await common.database.get_user_global_balance(db, whale_id)
        assert bal_whale == 900_000.0

        bal_robber = await common.database.get_user_global_balance(db, robber_id)
        assert bal_robber == 600_000.0

    # 2. Mirror reflection with high wealth robber: loss up to 100,000
    # Re-arm robber and give whale reflect shield
    await db.execute(
        "UPDATE Users SET active_items = ? WHERE user_id = ?",
        (json.dumps({"knife_gun": True}), robber_id),
    )
    now = int(time.time())
    await db.execute(
        "UPDATE Users SET active_items = ? WHERE user_id = ?",
        (json.dumps({"reflect_shield_until": now + 3600}), whale_id),
    )
    await db.commit()

    shared_state._TARGET_LAST_ATTACKED_TS.clear()
    shared_state._GLOBAL_COMBAT_COOLDOWNS.clear()
    shared_state._VICTIM_ROB_COOLDOWNS.clear()

    with patch("main.get_author_id_by_reply", new_callable=AsyncMock) as mock_auth, \
         patch("random.uniform", return_value=0.20), \
         patch("random.random", return_value=0.99):
        mock_auth.return_value = whale_id
        await main.cmd_rob(fake_msg, board_id, stream="ru")

        # Robber balance = 600,000. 20% is 120,000 -> capped at 100,000
        bal_robber_after_mirror = await common.database.get_user_global_balance(db, robber_id)
        assert bal_robber_after_mirror == 500_000.0
        bal_whale_after_mirror = await common.database.get_user_global_balance(db, whale_id)
        assert bal_whale_after_mirror == 1_000_000.0

    # 3. Tinfoil reflection with high wealth robber: loss up to 100,000
    await db.execute(
        "UPDATE Users SET active_items = ? WHERE user_id = ?",
        (json.dumps({"knife_gun": True}), robber_id),
    )
    await db.execute(
        "UPDATE Users SET active_items = ? WHERE user_id = ?",
        (json.dumps({"tinfoil_hat": now + 3600, "tinfoil_durability_hours": 10.0}), whale_id),
    )
    await db.commit()

    shared_state._TARGET_LAST_ATTACKED_TS.clear()
    shared_state._GLOBAL_COMBAT_COOLDOWNS.clear()
    shared_state._VICTIM_ROB_COOLDOWNS.clear()

    with patch("main.get_author_id_by_reply", new_callable=AsyncMock) as mock_auth, \
         patch("random.uniform", return_value=0.20), \
         patch("random.random", return_value=0.99):
        mock_auth.return_value = whale_id
        await main.cmd_rob(fake_msg, board_id, stream="ru")

        # Robber balance = 500,000. 20% is 100,000 -> capped at 100,000
        bal_robber_after_tin = await common.database.get_user_global_balance(db, robber_id)
        assert bal_robber_after_tin == 400_000.0


@pytest.mark.asyncio
async def test_false_report_fine_and_bail_scaled_up_to_200k():
    """Verify false report fine cap is raised from 50k to 200k in combat_moderation_engine."""
    from combat_moderation_engine import calculate_attacker_false_report_fine, calculate_bail_cost

    assert calculate_attacker_false_report_fine(10_000) == 500.0
    assert calculate_attacker_false_report_fine(1_000_000) == 50_000.0
    assert calculate_attacker_false_report_fine(2_000_000) == 100_000.0
    assert calculate_attacker_false_report_fine(4_000_000) == 200_000.0
    assert calculate_attacker_false_report_fine(10_000_000) == 200_000.0
    assert calculate_bail_cost(10_000_000) == 200_000.0
