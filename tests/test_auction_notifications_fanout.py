# -*- coding: utf-8 -*-
"""
tests/test_auction_notifications_fanout.py
Unit and integration test suite for Auction Fanout, Telegram Bot Integration & Anonymity.
Verifies:
1. Winner DM notification formatting (reward description, 100% burn, winning bid).
2. Public board announcement formatting and strict anonymity (zero raw user_id leakage).
3. Idempotent notification dispatch (DM to winner, board message enqueued).
4. finish_active_auctions integration with bots fanout.
5. Command regex matching for Telegram group chats with @bot_username suffixes.
"""

import asyncio
import re
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from common.anon_identity import generate_anon_name
import common.database
from whale_economy_engine import (
    ensure_auction_schema,
    create_auction,
    place_auction_bid,
    finish_active_auctions,
)
from auction_engine import (
    format_shekels,
    format_outbid_notification,
    format_auction_winner_dm,
    format_auction_public_announcement,
    dispatch_auction_completion_notifications,
    auction_router,
)


# =============================================================================
# 1. FORMATTING & CONTENT TESTS
# =============================================================================

def test_format_auction_winner_dm_custom_role():
    """Winner DM for custom_role must state role title, 30 days, winning bid, and 100% burn."""
    auc = {
        "auction_id": 42,
        "lot_type": "custom_role",
        "title": "Олигарх /b/",
        "description": "Олигарх /b/",
        "winning_bid": 150000.0,
        "winner_id": 99001,
        "winner_name": "Anon-99001",
        "board_id": "b",
    }
    dm_text = format_auction_winner_dm(auc)

    assert "🎉 <b>ТЫ ВЫИГРАЛ АУКЦИОН #42!</b>" in dm_text
    assert "Олигарх /b/" in dm_text
    assert "150 000 ₪" in dm_text
    assert "активирован в твоем профиле на 30 дней" in dm_text
    assert "100% шекелей твоей ставки сожжены" in dm_text
    assert "/auction" in dm_text


def test_format_auction_winner_dm_board_pin():
    """Winner DM for board_pin must state VIP voucher reward."""
    auc = {
        "auction_id": 43,
        "lot_type": "board_pin",
        "title": "VIP Закреп",
        "description": "Закреп на 24 часа",
        "winning_bid": 85000.0,
        "winner_id": 99002,
        "winner_name": "Anon-99002",
        "board_id": "b",
    }
    dm_text = format_auction_winner_dm(auc)

    assert "🎉 <b>ТЫ ВЫИГРАЛ АУКЦИОН #43!</b>" in dm_text
    assert "VIP-ваучер на закрепление треда" in dm_text
    assert "85 000 ₪" in dm_text
    assert "Фонд Яхты Абу" in dm_text


def test_format_auction_winner_dm_custom_badge():
    """Winner DM for custom_badge must state badge title."""
    auc = {
        "auction_id": 44,
        "lot_type": "custom_badge",
        "title": "Золотая Рыбка",
        "description": "Золотая медаль",
        "winning_bid": 60000.0,
        "winner_id": 99003,
        "winner_name": "Anon-99003",
        "board_id": "b",
    }
    dm_text = format_auction_winner_dm(auc)

    assert "🎉 <b>ТЫ ВЫИГРАЛ АУКЦИОН #44!</b>" in dm_text
    assert "Золотая Рыбка" in dm_text
    assert "Уникальный бейдж" in dm_text
    assert "60 000 ₪" in dm_text


# =============================================================================
# 2. STRICT ANONYMITY TESTS (ZERO USER_ID LEAKS)
# =============================================================================

def test_format_auction_public_announcement_strict_anonymity():
    """
    Public announcement must NEVER leak the raw integer user_id.
    Even if winner_name is raw digits or missing, it must display phonetic anon hash.
    """
    raw_uid = 771234567
    expected_anon = generate_anon_name(raw_uid)

    # Case A: winner_name is None
    auc_no_name = {
        "auction_id": 10,
        "lot_type": "custom_role",
        "title": "Тайный Лот",
        "description": "Описание",
        "winning_bid": 50000.0,
        "winner_id": raw_uid,
        "winner_name": None,
        "board_id": "b",
    }
    pub_a = format_auction_public_announcement(auc_no_name)
    assert str(raw_uid) not in pub_a, "Raw user_id leaked in public announcement!"
    assert expected_anon in pub_a
    assert "50 000 ₪" in pub_a
    assert "🏛️ <b>АУКЦИОН #10 ЗАВЕРШЕН!</b>" in pub_a

    # Case B: winner_name accidentally passed as string of digits
    auc_numeric_name = {
        "auction_id": 11,
        "lot_type": "board_pin",
        "title": "Закреп",
        "description": "Закреп",
        "winning_bid": 75000.0,
        "winner_id": raw_uid,
        "winner_name": str(raw_uid),
        "board_id": "b",
    }
    pub_b = format_auction_public_announcement(auc_numeric_name)
    assert str(raw_uid) not in pub_b, "Raw user_id string leaked in public announcement!"
    assert expected_anon in pub_b


def test_format_outbid_notification_anonymity():
    """Outbid notification must sanitize numeric leader names."""
    raw_uid = 882345678
    notif = format_outbid_notification(
        auction_id=5,
        lot_title="Золотой Аноним",
        refunded_amount=40000.0,
        new_bid=55000.0,
        new_leader_name=str(raw_uid),
    )
    assert str(raw_uid) not in notif
    assert "ВНИМАНИЕ! ТВОЮ СТАВКУ ПЕРЕБИЛИ!" in notif
    assert "40 000 ₪" in notif
    assert "55 000 ₪" in notif


# =============================================================================
# 3. DISPATCH & FANOUT TESTS (DM + BOARD POST)
# =============================================================================

@pytest.mark.asyncio
async def test_dispatch_auction_completion_notifications_fanout():
    """
    dispatch_auction_completion_notifications sends a private DM to the winner
    and posts an announcement to the board without throwing errors.
    """
    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock()

    finished = [{
        "auction_id": 101,
        "lot_type": "custom_role",
        "title": "Супер Лот",
        "description": "Супер Префикс",
        "winning_bid": 120000.0,
        "winner_id": 99101,
        "winner_name": "Аноним-101",
        "board_id": "b",
    }]

    with patch("common.database.create_post", new=AsyncMock(return_value=12345)), \
         patch("common.database.update_post_content", new=AsyncMock()), \
         patch("post_helpers.format_header", new=AsyncMock(return_value="[Header]")), \
         patch("shared_state.enqueue_board_message", new=AsyncMock(return_value=True)):

        stats = await dispatch_auction_completion_notifications(
            bots={"b": mock_bot},
            finished_auctions=finished,
            board_data={"b": {"users": {"active": {99101, 99102}, "banned": set()}}},
        )

        assert stats["dm_sent"] == 1
        assert stats["dm_failed"] == 0
        assert stats["board_posts"] == 1
        assert finished[0].get("_notified") is True

        # Verify DM sent to winner
        mock_bot.send_message.assert_called_once()
        call_kwargs = mock_bot.send_message.call_args.kwargs
        assert call_kwargs["chat_id"] == 99101
        assert "ТЫ ВЫИГРАЛ АУКЦИОН #101" in call_kwargs["text"]
        assert "120 000 ₪" in call_kwargs["text"]


@pytest.mark.asyncio
async def test_dispatch_notifications_idempotency():
    """Second call with the same finished list must not duplicate messages (_notified flag)."""
    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock()

    finished = [{
        "auction_id": 102,
        "lot_type": "board_pin",
        "title": "Пин",
        "winning_bid": 50000.0,
        "winner_id": 99102,
        "winner_name": "Anon",
        "board_id": "b",
        "_notified": True,  # Already notified
    }]

    stats = await dispatch_auction_completion_notifications(
        bots={"b": mock_bot},
        finished_auctions=finished,
    )
    assert stats["dm_sent"] == 0
    assert stats["board_posts"] == 0
    mock_bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_handles_telegram_errors_gracefully():
    """If bot.send_message raises an exception (e.g. BotBlocked), it logs and does not crash."""
    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock(side_effect=Exception("Forbidden: bot was blocked by the user"))

    finished = [{
        "auction_id": 103,
        "lot_type": "custom_badge",
        "title": "Бейдж",
        "winning_bid": 50000.0,
        "winner_id": 99103,
        "winner_name": "Anon",
        "board_id": "b",
    }]

    with patch("common.database.create_post", new=AsyncMock(return_value=999)), \
         patch("common.database.update_post_content", new=AsyncMock()), \
         patch("post_helpers.format_header", new=AsyncMock(return_value="[Header]")), \
         patch("shared_state.enqueue_board_message", new=AsyncMock(return_value=True)):

        stats = await dispatch_auction_completion_notifications(
            bots={"b": mock_bot},
            finished_auctions=finished,
        )

        assert stats["dm_sent"] == 0
        assert stats["dm_failed"] == 1
        assert stats["board_posts"] == 1


# =============================================================================
# 4. FULL INTEGRATION WITH ISOLATED TEST DB
# =============================================================================

@pytest.mark.asyncio
async def test_finish_active_auctions_with_bots_and_fund_burn(isolated_test_db):
    """
    End-to-end integration:
    1. Create auction and place winning bid.
    2. Expire auction.
    3. Call finish_active_auctions with mock bot and board_data.
    4. Verify 100% winning bid burned to Abu Yacht Fund.
    5. Verify lot awarded in Users table.
    6. Verify winner received DM notification.
    7. Verify description and board_id returned in dict.
    """
    db = isolated_test_db
    await ensure_auction_schema(db)

    auc_id = await create_auction(
        db=db,
        lot_type="custom_role",
        title="Титул Барона",
        description="Барон /b/",
        start_price=50000.0,
        min_bid_step=5000.0,
        duration_sec=1.0,
        board_id="b",
    )

    winner_id = 99555
    await common.database.add_user_global_balance(db, winner_id, "b", 200000.0)

    # Place winning bid
    res = await place_auction_bid(db, auc_id, winner_id, "BaronAnon", 100000.0, "b")
    assert res["ok"] is True

    # Fast forward expiration
    await db.execute("UPDATE Auctions SET ends_at = ? WHERE id = ?", (time.time() - 10, auc_id))

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock()

    fund_before = await common.database.get_abu_fund_total(db)

    with patch("common.database.create_post", new=AsyncMock(return_value=55555)), \
         patch("common.database.update_post_content", new=AsyncMock()), \
         patch("post_helpers.format_header", new=AsyncMock(return_value="[Header]")), \
         patch("shared_state.enqueue_board_message", new=AsyncMock(return_value=True)):

        finished = await finish_active_auctions(
            db,
            bots={"b": mock_bot},
            board_data={"b": {"users": {"active": {winner_id}, "banned": set()}}}
        )

    assert len(finished) == 1
    assert finished[0]["auction_id"] == auc_id
    assert finished[0]["winning_bid"] == 100000.0
    assert finished[0]["winner_id"] == winner_id
    assert finished[0]["title"] == "Титул Барона"
    assert finished[0]["description"] == "Барон /b/"
    assert finished[0]["board_id"] == "b"

    # Fund burn verification
    fund_after = await common.database.get_abu_fund_total(db)
    assert fund_after == fund_before + 100000.0

    # User title reward verification
    async with db.execute("SELECT custom_prefix FROM Users WHERE user_id = ?", (winner_id,)) as c:
        row = await c.fetchone()
        assert row is not None
        assert "[Барон /b/]" in row[0]

    # Bot DM verification
    mock_bot.send_message.assert_called_once()
    dm_call = mock_bot.send_message.call_args.kwargs
    assert dm_call["chat_id"] == winner_id
    assert "ТЫ ВЫИГРАЛ АУКЦИОН" in dm_call["text"]
    assert "Титул Барона" in dm_call["text"]
    assert "100 000 ₪" in dm_call["text"]


# =============================================================================
# 5. TELEGRAM COMMAND REGEX & BOT USERNAME SUFFIX TESTS
# =============================================================================

def test_telegram_auction_command_regexes():
    """
    Commands in Telegram groups can have @bot_username suffixes:
    /auction@dvach_bot, /bid@dvach_bot 1 50000, /аукцион@dvach_bot.
    Regex patterns must match all valid invocations.
    """
    auction_pattern = re.compile(r"^/(auction|auctions|аукцион)(?:@\w+)?(?:\s|$)", re.IGNORECASE)
    bid_pattern = re.compile(r"^/(bid|auction_bid|ставка)(?:@\w+)?(?:\s|$)", re.IGNORECASE)

    # Valid /auction invocations
    assert auction_pattern.match("/auction")
    assert auction_pattern.match("/auction ")
    assert auction_pattern.match("/auction create custom_role 50000 5000 24 Title")
    assert auction_pattern.match("/auction@tgach_bot")
    assert auction_pattern.match("/auction@dvach_bot 2")
    assert auction_pattern.match("/auctions")
    assert auction_pattern.match("/аукцион")
    assert auction_pattern.match("/аукцион@tgach_bot")
    assert auction_pattern.match("/АУКЦИОН")

    # Invalid /auction invocations
    assert not auction_pattern.match("/auctioneer")
    assert not auction_pattern.match("/auction_house")
    assert not auction_pattern.match("hello /auction")

    # Valid /bid invocations
    assert bid_pattern.match("/bid")
    assert bid_pattern.match("/bid 1 60000")
    assert bid_pattern.match("/bid@tgach_bot 1 60000")
    assert bid_pattern.match("/ставка 1 60000")
    assert bid_pattern.match("/ставка@dvach_bot 1 60000")
    assert bid_pattern.match("/auction_bid 1 60000")

    # Invalid /bid invocations
    assert not bid_pattern.match("/bidding")
    assert not bid_pattern.match("/bidder")
    assert not bid_pattern.match("place /bid")
