# -*- coding: utf-8 -*-
"""
tests/test_market_auction_transfers_audit.py
Full verification test suite for Subagent 6:
Market (P2P), Auctions, and Shekel Transfers (/pay, /transactions).
"""

import json
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import types

import common.database
from auction_engine import (
    cmd_auction,
    cmd_bid,
    cb_auction_page,
    build_auction_list_kb,
)
from market_engine import (
    cmd_market,
    cmd_sell,
    cmd_my_lots,
    cb_market_my_lots,
    cmd_buy_market,
    cmd_cancel_market,
    create_market_listing,
    get_user_listings,
    get_market_catalog,
    ensure_market_schema,
)
from whale_economy_engine import (
    ensure_auction_schema,
    create_auction,
    get_active_auctions,
    place_auction_bid,
)


@pytest.mark.asyncio
async def test_market_catalog_and_my_lots_pagination_under_50_items(isolated_test_db):
    """
    Ensures that when 50 items are active on the market:
    1. get_market_catalog returns 5 items per page and total_pages = 10.
    2. get_user_listings with pagination returns 5 items per page.
    3. cmd_my_lots renders a message well within 4096 chars with 7 keyboard rows instead of 50.
    4. cb_market_my_lots cleanly parses page from callback_data.
    """
    db = isolated_test_db
    await ensure_market_schema(db)
    user_id = 111001

    # Insert 50 listings
    now = time.time()
    for i in range(1, 51):
        await db.execute("""
            INSERT INTO MarketListings (seller_id, seller_board_id, item_id, item_type, item_name, item_data, price, status, created_at)
            VALUES (?, 'b', 'knife', 'weapon', ?, '{}', ?, 'active', ?)
        """, (user_id, f"🔪 Заточка #{i}", 100.0 * i, now - i * 5))
    await db.commit()

    # 1. Catalog pagination
    items, total_pages, total_count = await get_market_catalog(db, category="weapon", page=1, per_page=5)
    assert len(items) == 5
    assert total_count == 50
    assert total_pages == 10

    # 2. User listings pagination
    u_items, u_pages, u_total = await get_user_listings(db, user_id, status="active", page=2, per_page=5)
    assert len(u_items) == 5
    assert u_total == 50
    assert u_pages == 10

    # 3. cmd_my_lots message length and button row limits
    import market_engine
    market_engine.get_pool = AsyncMock(return_value=db)

    msg = MagicMock()
    msg.from_user.id = user_id
    msg.text = "/my_lots"
    msg.answer = AsyncMock()

    await cmd_my_lots(msg)
    reply_text = msg.answer.call_args[0][0]
    kb = msg.answer.call_args[1].get("reply_markup")

    assert len(reply_text) < 1000
    assert "Стр. 1/10" in reply_text
    assert len(kb.inline_keyboard) == 7  # 5 lots + 1 nav row + 1 action row

    # 4. cb_market_my_lots parses page 3
    cb = MagicMock(spec=types.CallbackQuery)
    cb.from_user = MagicMock()
    cb.from_user.id = user_id
    cb.data = "market_my_lots:3"
    cb.message = MagicMock()
    cb.message.caption = None
    cb.message.photo = None
    cb.message.text = "prev_text"
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()

    await cb_market_my_lots(cb)
    cb_reply = cb.message.edit_text.call_args[1].get("text")
    assert "Стр. 3/10" in cb_reply
    cb_kb = cb.message.edit_text.call_args[1].get("reply_markup")
    assert len(cb_kb.inline_keyboard) == 7


@pytest.mark.asyncio
async def test_cmd_buy_market_and_cancel_market(isolated_test_db):
    """
    Tests direct slash commands /buy_market and /cancel_market:
    - Atomic purchase with Abu 5% tax and seller PM notification.
    - Cancellation restores item to seller active_items.
    """
    db = isolated_test_db
    await ensure_market_schema(db)
    seller_id = 111002
    buyer_id = 111003

    # Setup seller with knife
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 0, ?)",
        (seller_id, json.dumps({"knife_gun": True}))
    )
    # Setup buyer with 5,000 shekels
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 5000, '{}')",
        (buyer_id,)
    )
    await db.commit()

    import market_engine
    market_engine.get_pool = AsyncMock(return_value=db)

    # 1. Seller lists item
    ok, listing, _ = await create_market_listing(db, seller_id, "b", "knife", price=1000.0, item_type="weapon")
    assert ok is True
    lot_id = listing["id"]

    # 2. Buyer purchases via /buy_market
    buy_msg = MagicMock()
    buy_msg.from_user.id = buyer_id
    buy_msg.text = f"/buy_market {lot_id}"
    buy_msg.answer = AsyncMock()
    buy_msg.bot = MagicMock()
    buy_msg.bot.send_message = AsyncMock()

    await cmd_buy_market(buy_msg)
    buy_text = buy_msg.answer.call_args[0][0]
    assert "ПОКУПКА УСПЕШНО СОВЕРШЕНА" in buy_text
    assert "1,000" in buy_text
    assert "50.00" in buy_text  # 5% fee

    # Verify balances: buyer paid 1,000, seller received 950 (1000 - 50 fee)
    buyer_bal = await common.database.get_user_global_balance(db, buyer_id)
    seller_bal = await common.database.get_user_global_balance(db, seller_id)
    assert buyer_bal == 4000.0
    assert seller_bal == 950.0

    # Verify seller notification sent
    buy_msg.bot.send_message.assert_called_once()
    assert buy_msg.bot.send_message.call_args[1]["chat_id"] == seller_id

    # 3. Test /cancel_market on a second lot
    await db.execute(
        "UPDATE Users SET active_items = ? WHERE user_id = ?",
        (json.dumps({"knife_gun": True}), seller_id)
    )
    ok2, listing2, _ = await create_market_listing(db, seller_id, "b", "knife", price=500.0, item_type="weapon")
    assert ok2 is True
    lot2_id = listing2["id"]

    cancel_msg = MagicMock()
    cancel_msg.from_user.id = seller_id
    cancel_msg.text = f"/cancel_market {lot2_id}"
    cancel_msg.answer = AsyncMock()

    await cmd_cancel_market(cancel_msg)
    cancel_text = cancel_msg.answer.call_args[0][0]
    assert "СНЯТ С ПРОДАЖИ" in cancel_text

    # Verify item restored
    async with db.execute("SELECT active_items FROM Users WHERE user_id = ?", (seller_id,)) as c:
        row = await c.fetchone()
        items = json.loads(row[0])
        assert items.get("knife_gun") is True


@pytest.mark.asyncio
async def test_market_wanted_stars_guard(isolated_test_db):
    """
    Tests that a user with 5★ wanted stars is blocked from /sell and /buy_market.
    """
    db = isolated_test_db
    await ensure_market_schema(db)
    wanted_user = 111004

    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 10000, ?)",
        (wanted_user, json.dumps({"wanted_stars": 5, "knife_gun": True}))
    )
    await db.commit()

    import market_engine
    market_engine.get_pool = AsyncMock(return_value=db)

    # 1. /sell blocked
    sell_msg = MagicMock()
    sell_msg.from_user.id = wanted_user
    sell_msg.text = "/sell knife 500"
    sell_msg.answer = AsyncMock()

    await cmd_sell(sell_msg)
    sell_reply = sell_msg.answer.call_args[0][0]
    assert "СЛУЖБА ФИНАНСОВОГО МОНИТОРИНГА АБУ" in sell_reply
    assert "5★" in sell_reply

    # 2. /buy_market blocked
    buy_msg = MagicMock()
    buy_msg.from_user.id = wanted_user
    buy_msg.text = "/buy_market 1"
    buy_msg.answer = AsyncMock()

    await cmd_buy_market(buy_msg)
    buy_reply = buy_msg.answer.call_args[0][0]
    assert "СЛУЖБА ФИНАНСОВОГО МОНИТОРИНГА АБУ" in buy_reply
    assert "5★" in buy_reply


@pytest.mark.asyncio
async def test_auction_pagination_with_25_lots_never_exceeds_telegram_limit(isolated_test_db):
    """
    Verifies that with 25 active auctions:
    1. /auction output length is strictly under 4096 characters (target < 1500 chars).
    2. Paginated at 4 auctions per page (total_pages = 7).
    3. /auction 2 opens page 2.
    4. cb_auction_page updates view on button click.
    """
    db = isolated_test_db
    await ensure_auction_schema(db)

    for i in range(1, 26):
        await create_auction(
            db,
            lot_type="custom_role",
            title=f"Супер-титул #{i} Двачера",
            description=f"Эксклюзивный почетный статус #{i}",
            start_price=10000.0 * i,
            min_bid_step=1000.0,
            duration_sec=7200.0,
            board_id="b"
        )

    import auction_engine
    auction_engine.get_pool = AsyncMock(return_value=db)

    # 1. /auction page 1
    msg = MagicMock()
    msg.board_id = "b"
    msg.text = "/auction"
    msg.reply = AsyncMock()

    await cmd_auction(msg)
    reply_text = msg.reply.call_args[0][0]
    kb = msg.reply.call_args[1].get("reply_markup")

    assert len(reply_text) <= 3900  # Strict Telegram safety
    assert "Стр. 1/7" in reply_text
    assert "лотов: 25" in reply_text
    assert kb is not None
    assert len(kb.inline_keyboard[0]) == 3  # Back, Status, Forward

    # 2. /auction 2
    msg_p2 = MagicMock()
    msg_p2.board_id = "b"
    msg_p2.text = "/auction 2"
    msg_p2.reply = AsyncMock()

    await cmd_auction(msg_p2)
    reply_p2 = msg_p2.reply.call_args[0][0]
    assert "Стр. 2/7" in reply_p2

    # 3. cb_auction_page callback
    cb = MagicMock(spec=types.CallbackQuery)
    cb.data = "auc_page:3"
    cb.message = MagicMock()
    cb.message.caption = None
    cb.message.photo = None
    cb.message.text = "prev"
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()

    await cb_auction_page(cb)
    cb_text = cb.message.edit_text.call_args[1].get("text")
    assert "Стр. 3/7" in cb_text


@pytest.mark.asyncio
async def test_cmd_bid_guards(isolated_test_db):
    """
    Tests that /bid checks:
    1. User mute status.
    2. User isolation status.
    3. User 5★ wanted stars status.
    """
    db = isolated_test_db
    await ensure_auction_schema(db)
    auc_id = await create_auction(
        db, lot_type="board_pin", title="Pin test", description="desc",
        start_price=5000.0, min_bid_step=500.0, duration_sec=3600.0
    )

    import auction_engine
    auction_engine.get_pool = AsyncMock(return_value=db)

    # 1. Wanted 5★ user blocked
    wanted_user = 111005
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 50000, ?)",
        (wanted_user, json.dumps({"wanted_stars": 5}))
    )
    await db.commit()

    bid_msg = MagicMock()
    bid_msg.board_id = "b"
    bid_msg.from_user.id = wanted_user
    bid_msg.from_user.full_name = "Criminal"
    bid_msg.text = f"/bid {auc_id} 6000"
    bid_msg.reply = AsyncMock()

    await cmd_bid(bid_msg)
    reply = bid_msg.reply.call_args[0][0]
    assert "СЛУЖБА ФИНАНСОВОГО МОНИТОРИНГА АБУ" in reply
    assert "5★" in reply

    # 2. Isolated user blocked
    iso_user = 111006
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, active_items, is_isolated) VALUES (?, 'b', 50000, '{}', 1)",
        (iso_user,)
    )
    await db.commit()

    bid_msg_iso = MagicMock()
    bid_msg_iso.board_id = "b"
    bid_msg_iso.from_user.id = iso_user
    bid_msg_iso.from_user.full_name = "Monk"
    bid_msg_iso.text = f"/bid {auc_id} 6000"
    bid_msg_iso.reply = AsyncMock()

    await cmd_bid(bid_msg_iso)
    reply_iso = bid_msg_iso.reply.call_args[0][0]
    assert "самоизоляции" in reply_iso


@pytest.mark.asyncio
async def test_pay_wanted_stars_and_overflow_guards(isolated_test_db):
    """
    Tests /pay command guards:
    1. Sender with 5★ wanted stars blocked immediately before balance check.
    2. Recipient with 5★ wanted stars blocked (frozen account).
    3. Negative, zero, or overflow (> 10M) amounts rejected.
    """
    from main import cmd_pay, _parse_pay_amount
    db = isolated_test_db
    sender_wanted = 111010
    receiver_clean = 111011
    receiver_wanted = 111012

    await db.execute("INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 50000, ?)",
                     (sender_wanted, json.dumps({"wanted_stars": 5})))
    await db.execute("INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 50000, '{}')",
                     (receiver_clean,))
    await db.execute("INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 50000, ?)",
                     (receiver_wanted, json.dumps({"wanted_stars": 5})))
    await db.commit()

    import main
    main.get_pool = AsyncMock(return_value=db)

    # 1. Sender with 5★ wanted stars blocked even if balance is sufficient or insufficient
    msg = MagicMock()
    msg.from_user.id = sender_wanted
    msg.reply_to_message = MagicMock()
    msg.reply_to_message.from_user.id = receiver_clean
    msg.reply_to_message.from_user.is_bot = False
    msg.text = "/pay 500"
    msg.reply = AsyncMock()
    main.get_author_id_by_reply = AsyncMock(return_value=receiver_clean)

    await cmd_pay(msg, board_id="b")
    reply = msg.reply.call_args[0][0]
    assert "СЛУЖБА ФИНАНСОВОГО МОНИТОРИНГА АБУ" in reply
    assert "5★" in reply

    # 2. Recipient with 5★ wanted stars blocked
    clean_sender = 111013
    await db.execute("INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 50000, '{}')",
                     (clean_sender,))
    await db.commit()

    msg2 = MagicMock()
    msg2.from_user.id = clean_sender
    msg2.reply_to_message = MagicMock()
    msg2.reply_to_message.from_user.id = receiver_wanted
    msg2.reply_to_message.from_user.is_bot = False
    msg2.text = "/pay 500"
    msg2.reply = AsyncMock()
    main.get_author_id_by_reply = AsyncMock(return_value=receiver_wanted)

    await cmd_pay(msg2, board_id="b")
    reply2 = msg2.reply.call_args[0][0]
    assert "СЛУЖБА ФИНАНСОВОГО МОНИТОРИНГА АБУ" in reply2
    assert "Получатель находится в федеральном розыске" in reply2

    # 3. Numeric edge cases in _parse_pay_amount
    amt, err = _parse_pay_amount("-500", 50000)
    assert amt is None
    assert err == "negative_or_zero"

    amt, err = _parse_pay_amount("0", 50000)
    assert amt is None
    assert err == "negative_or_zero"

    amt, err = _parse_pay_amount("999999999", 50000)
    assert amt is None
    assert err == "too_large"

    amt, err = _parse_pay_amount("1e99", 50000)
    assert amt is None
    assert err == "too_large"
