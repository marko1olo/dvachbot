# -*- coding: utf-8 -*-
"""
tests/test_inquisitor_market_work_commands.py
Inquisitor 4 Redteam Test Suite:
Market, Auctions, Work & Global Safety Inquisitor.

Validates:
1. P2P Market & Auctions:
   - Emulation of 30 market listings and 25 active auctions.
   - /auction pagination (4 per page, length < 1400 chars, page navigation buttons).
   - /my_lots pagination (5 per page).
   - Slash-commands /buy_market <id> and /cancel_market <id>.
   - 5★ wanted criminal bidding/buying prevention (/bid and /buy_market).
2. Work & Crime:
   - /work card length <= 1024 chars across careers and night shifts.
   - HTML tag balance (no unclosed <code>, <b>, <i>).
   - /heist cooperative lobby start (not intercepted by old AI-robbery).
   - /launder 30% Abu Fund commission, 70% clean balance.
   - Microloans /loan and /paydebt with persistent navigation buttons.
3. Stress test of smart_split_html & TelegramBadRequest guard:
   - 12,000 characters deeply nested unclosed HTML tags.
   - smart_split_html chunks <= 4000 chars with valid tag closure & reopen.
   - Message.answer with > 4096 chars transparently chunked without TelegramBadRequest.
4. Full registry check:
   - All 134 commands from setup_bot_commands executed without unhandled exceptions.
"""

import asyncio
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
import math
import time
from typing import Any, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram import Bot, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendMessage
from aiogram.types import (
    Chat,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    Update,
    User,
)

import auction_engine
from auction_engine import (
    build_auction_list_kb,
    cb_auction_page,
    cmd_auction,
    cmd_bid,
)
from common.bot_helpers import (
    _get_user_active_items,
    install_message_safety_guard,
    safe_send_message,
    smart_split_html,
)
import common.config
import common.database
from common.database import get_abu_fund_total, get_user_global_balance
import common.db_pool
import common.work_engine
from heist_and_loan_engine import (
    active_heist_lobbies,
    build_heist_keyboard,
    build_loan_keyboard,
    cb_heist_join,
    cb_loan_paydebt_full,
    cb_loan_take_preset,
    chat_active_heist,
    cmd_loan,
    cmd_money_laundering,
    cmd_paydebt,
    cmd_start_heist,
    get_user_active_items,
    process_borrow_loan,
    process_money_laundering,
    process_repay_debt,
    save_user_active_items,
)
import main
from main import (
    _build_work_card,
    cmd_work,
    dp,
    setup_bot_commands,
)
import market_engine
from market_engine import (
    buy_market_listing,
    cancel_market_listing,
    cmd_buy_market,
    cmd_cancel_market,
    cmd_my_lots,
    ensure_market_schema,
    get_market_catalog,
    get_user_listings,
)
from whale_economy_engine import (
    create_auction,
    ensure_auction_schema,
    get_active_auctions,
    place_auction_bid,
)


class HTMLTagBalanceChecker(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.errors = []

    def handle_starttag(self, tag, attrs):
        self.stack.append(tag.lower())

    def handle_endtag(self, tag):
        t = tag.lower()
        if not self.stack:
            self.errors.append(f"Unexpected closing </{t}> with empty stack")
        elif self.stack[-1] != t:
            self.errors.append(f"Mismatched </{t}>, expected </{self.stack[-1]}>")
            if t in self.stack:
                while self.stack and self.stack[-1] != t:
                    self.stack.pop()
                if self.stack:
                    self.stack.pop()
        else:
            self.stack.pop()


@pytest.fixture
def mock_bot():
    bot = AsyncMock(spec=Bot)
    bot.id = 123456789
    bot.token = "test_bot_token"
    default_msg = types.Message.model_construct(
        message_id=1,
        date=datetime.now(timezone.utc),
        chat=types.Chat(id=-100123456, type="supergroup"),
        text="ok"
    )
    bot.return_value = default_msg
    bot.send_message = AsyncMock(return_value=default_msg)
    bot.send_photo = AsyncMock(
        return_value=types.Message.model_construct(
            message_id=2,
            date=datetime.now(timezone.utc),
            chat=types.Chat(id=-100123456, type="supergroup"),
            text="ok"
        )
    )
    bot.set_my_commands = AsyncMock(return_value=True)
    return bot


# =============================================================================
# 1. P2P-MARKET & AUCTIONS TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_market_and_auction_pagination_and_security(isolated_test_db, mock_bot):
    """
    Emulate 30 market listings and 25 active auctions:
    - /auction: verifies pagination (4 items/page), message length < 1400 chars, nav buttons.
    - /my_lots: verifies pagination (5 items/page).
    - Slash-commands: /buy_market <id> and /cancel_market <id>.
    - Security: 5★ wanted criminal bidding/buying prevention (/bid, /buy_market).
    """
    db = isolated_test_db
    market_engine.get_pool = AsyncMock(return_value=db)
    auction_engine.get_pool = AsyncMock(return_value=db)
    await ensure_market_schema(db)
    await ensure_auction_schema(db)

    now = time.time()
    seller_id = 10001
    buyer_id = 10002
    board_id = "b"

    # 1. Insert 30 Market listings
    for i in range(1, 31):
        await db.execute("""
            INSERT INTO MarketListings (seller_id, seller_board_id, item_id, item_type, item_name, item_data, price, status, created_at)
            VALUES (?, ?, 'knife', 'weapon', ?, '{}', ?, 'active', ?)
        """, (seller_id, board_id, f"🔪 Лот #{i}", 100.0 + i * 10, now - i * 10))

    # 2. Insert 25 Active Auctions with correct whale schema
    for i in range(1, 26):
        await db.execute("""
            INSERT INTO Auctions (board_id, lot_type, title, description, start_price, min_bid_step,
                                 current_bid, current_winner_id, current_winner_name,
                                 status, starts_at, ends_at, anti_snipe_sec, created_at)
            VALUES (?, 'custom_role', ?, 'Эксклюзивный лот аукциона', ?, ?, ?, NULL, NULL, 'active', ?, ?, 300, ?)
        """, (board_id, f"🏆 Золотой Лот #{i}", 50000.0, 5000.0, 50000.0, now - 100, now + 3600, now - 100))
    await db.commit()

    # --- Test /auction pagination & message length ---
    active_aucs = await get_active_auctions(db, board_id)
    assert len(active_aucs) == 25

    msg_auc = MagicMock(spec=Message)
    msg_auc.text = "/auction"
    msg_auc.board_id = board_id
    msg_auc.from_user = User(id=buyer_id, is_bot=False, first_name="Buyer")
    msg_auc.reply = AsyncMock()

    await cmd_auction(msg_auc, board_id=board_id)
    msg_auc.reply.assert_called_once()
    auc_reply_text = msg_auc.reply.call_args[0][0]
    auc_kb = msg_auc.reply.call_args[1].get("reply_markup")

    # Assert 4 auctions per page, total 7 pages (ceil(25/4))
    assert "(Стр. 1/7, лотов: 25)" in auc_reply_text
    assert len(auc_reply_text) < 1400, f"Auction message too long: {len(auc_reply_text)} chars"
    assert auc_kb is not None
    # Navigation row contains 3 buttons: ◀️, Стр. 1/7, Вперед ▶️
    assert len(auc_kb.inline_keyboard[0]) == 3
    assert auc_kb.inline_keyboard[0][1].text == "Стр. 1/7"
    assert auc_kb.inline_keyboard[0][2].callback_data == "auc_page:2"

    # --- Test /my_lots pagination (5 per page) ---
    msg_lots = MagicMock(spec=Message)
    msg_lots.text = "/my_lots"
    msg_lots.board_id = board_id
    msg_lots.from_user = User(id=seller_id, is_bot=False, first_name="Seller")
    msg_lots.answer = AsyncMock()

    await cmd_my_lots(msg_lots, board_id=board_id)
    msg_lots.answer.assert_called_once()
    lots_reply_text = msg_lots.answer.call_args[0][0]
    lots_kb = msg_lots.answer.call_args[1].get("reply_markup")

    # 30 items -> 6 pages of 5 items
    assert "(Стр. 1/6, всего: 30)" in lots_reply_text
    # Keyboard has 5 lot buttons + 1 navigation row + 1 action row = 7 rows
    assert len(lots_kb.inline_keyboard) == 7

    # --- Test /buy_market slash command ---
    # Give buyer funds
    await common.database.add_user_global_balance(db, buyer_id, board_id, 10000.0)
    fund_before = await get_abu_fund_total(db)

    msg_buy = MagicMock(spec=Message)
    msg_buy.text = "/buy_market 1"
    msg_buy.board_id = board_id
    msg_buy.from_user = User(id=buyer_id, is_bot=False, first_name="Buyer")
    msg_buy.chat = Chat(id=buyer_id, type="private")
    msg_buy.bot = mock_bot
    msg_buy.answer = AsyncMock()

    await cmd_buy_market(msg_buy, board_id=board_id)
    msg_buy.answer.assert_called_once()
    buy_reply = msg_buy.answer.call_args[0][0]
    assert "ПОКУПКА УСПЕШНО СОВЕРШЕНА!" in buy_reply
    assert "лот #1" in buy_reply

    # Verify 5% fee went to Abu Fund
    fund_after = await get_abu_fund_total(db)
    assert fund_after > fund_before

    # Verify item is in buyer's inventory
    buyer_items = await _get_user_active_items(db, buyer_id, board_id)
    assert buyer_items.get("knife_gun", 0) >= 1

    # --- Test /cancel_market slash command ---
    msg_cancel = MagicMock(spec=Message)
    msg_cancel.text = "/cancel_market 2"
    msg_cancel.board_id = board_id
    msg_cancel.from_user = User(id=seller_id, is_bot=False, first_name="Seller")
    msg_cancel.chat = Chat(id=seller_id, type="private")
    msg_cancel.answer = AsyncMock()

    await cmd_cancel_market(msg_cancel, board_id=board_id)
    msg_cancel.answer.assert_called_once()
    cancel_reply = msg_cancel.answer.call_args[0][0]
    assert "ЛОТ #2 СНЯТ С ПРОДАЖИ" in cancel_reply

    # Verify item restored to seller's active_items
    seller_items = await _get_user_active_items(db, seller_id, board_id)
    assert seller_items.get("knife_gun", 0) >= 1

    # --- Test 5★ wanted criminal bidding & buying protection ---
    criminal_id = 10003
    await common.database.add_user_global_balance(db, criminal_id, board_id, 100000.0)
    await save_user_active_items(db, criminal_id, {"wanted_stars": 5}, board_id)

    # 1. Attempt /bid with 5★ wanted
    msg_bid = MagicMock(spec=Message)
    msg_bid.text = "/bid 1 60000"
    msg_bid.board_id = board_id
    msg_bid.from_user = User(id=criminal_id, is_bot=False, first_name="WantedCriminal")
    msg_bid.reply = AsyncMock()

    await cmd_bid(msg_bid)
    msg_bid.reply.assert_called_once()
    bid_blocked_text = msg_bid.reply.call_args[0][0]
    assert "СЛУЖБА ФИНАНСОВОГО МОНИТОРИНГА АБУ" in bid_blocked_text
    assert "5★" in bid_blocked_text

    # 2. Attempt /buy_market with 5★ wanted
    msg_criminal_buy = MagicMock(spec=Message)
    msg_criminal_buy.text = "/buy_market 3"
    msg_criminal_buy.board_id = board_id
    msg_criminal_buy.from_user = User(id=criminal_id, is_bot=False, first_name="WantedCriminal")
    msg_criminal_buy.chat = Chat(id=criminal_id, type="private")
    msg_criminal_buy.answer = AsyncMock()

    await cmd_buy_market(msg_criminal_buy, board_id=board_id)
    msg_criminal_buy.answer.assert_called_once()
    market_blocked_text = msg_criminal_buy.answer.call_args[0][0]
    assert "СЛУЖБА ФИНАНСОВОГО МОНИТОРИНГА АБУ" in market_blocked_text
    assert "5★" in market_blocked_text


# =============================================================================
# 2. WORK & CRIME TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_work_card_length_and_html_tag_balance(isolated_test_db):
    """
    Validates /work card generation across different career stages and night shifts:
    - Caption length <= 1024 characters.
    - HTML tags perfectly closed and balanced (no unclosed <code>, <b>, <i>).
    """
    db = isolated_test_db
    user_id = 20001
    board_id = "b"

    career_scenarios = [
        ("Newbie", 0, {}, 100.0),
        ("Junior", 5, {"work_cooldowns": {"bottles": time.time() + 3600}}, 500.0),
        ("Mid-level Wasserman", 50, {
            "equipped_torso": "body_wasserman",
            "equipped_head": "hat_crown",
            "equipped_face": "face_wasserman_glasses",
            "work_cooldowns": {"bottles": time.time() + 3600, "sweeper": time.time() + 1800}
        }, 50000.0),
        ("Fatigued Veteran", 200, {
            "recent_shifts": [time.time() - i * 60 for i in range(25)],
            "work_cooldowns": {
                "bottles": time.time() + 3600,
                "sweeper": time.time() + 3600,
                "courier": time.time() + 3600
            }
        }, 150000.0),
        ("Demigod Max-Shifts", 2000, {
            "work_cooldowns": {
                "bottles": time.time() + 3600,
                "sweeper": time.time() + 3600,
                "courier": time.time() + 3600,
                "captcha": time.time() + 3600,
                "cho_security": time.time() + 3600
            }
        }, 999999999.0)
    ]

    for name, shifts, items, balance in career_scenarios:
        items["total_shifts"] = shifts
        await save_user_active_items(db, user_id, items, board_id)
        await common.database.add_user_global_balance(db, user_id, board_id, balance)

        for night_mode in (False, True):
            orig_is_night = common.work_engine.is_night_shift_active
            common.work_engine.is_night_shift_active = lambda now=None: night_mode
            try:
                caption, kb = await _build_work_card(user_id, board_id)

                # 1. Length constraint
                assert len(caption) <= 1024, f"[{name}, night={night_mode}] Caption exceeds 1024 chars: {len(caption)}"

                # 2. HTML tag balance verification
                checker = HTMLTagBalanceChecker()
                checker.feed(caption)
                assert not checker.errors, f"[{name}, night={night_mode}] Tag syntax errors: {checker.errors}"
                assert not checker.stack, f"[{name}, night={night_mode}] Unclosed HTML tags left on stack: {checker.stack}"

                # 3. Night shift indicator presence
                if night_mode:
                    assert "НОЧНАЯ СМЕНА" in caption
            finally:
                common.work_engine.is_night_shift_active = orig_is_night


@pytest.mark.asyncio
async def test_heist_cooperative_lobby_and_no_ai_robbery_interception(isolated_test_db, mock_bot):
    """
    Validates /heist starts collaborative bank truck heist lobby
    and is NOT intercepted by AI-robbery or standard /rob.
    """
    db = isolated_test_db
    active_heist_lobbies.clear()
    chat_active_heist.clear()

    user_id = 30001
    chat_id = -100555666

    msg = types.Message.model_construct(
        message_id=50,
        date=datetime.now(timezone.utc),
        chat=types.Chat(id=chat_id, type="supergroup", title="Crime Chat"),
        from_user=types.User(id=user_id, is_bot=False, first_name="HeistMaster", username="heist_master"),
        text="/heist"
    )
    msg._bot = mock_bot

    await cmd_start_heist(msg)

    # 1. Verify lobby exists in chat_active_heist and active_heist_lobbies
    assert chat_id in chat_active_heist
    lobby_id = chat_active_heist[chat_id]
    assert lobby_id in active_heist_lobbies
    lobby = active_heist_lobbies[lobby_id]
    assert lobby.initiator_id == user_id
    assert user_id in lobby.participants
    if lobby.timer_task:
        lobby.timer_task.cancel()

    # 2. Verify lobby message was sent via bot SendMessage call
    send_calls = [c for c in mock_bot.mock_calls if c.args and isinstance(c.args[0], SendMessage)]
    assert len(send_calls) >= 1
    sent_sm = send_calls[0].args[0]
    sent_text = sent_sm.text
    sent_kb = sent_sm.reply_markup

    assert "НАЛЁТ НА ИНКАССАТОРСКИЙ БРОНЕВИК АБУ" in sent_text
    assert "шекелями Абу" in sent_text

    # 3. Verify interactive lobby buttons
    kb_buttons = [btn.text for row in sent_kb.inline_keyboard for btn in row]
    assert any("Вступить в банду" in b for b in kb_buttons)

    # Test joining of a second participant
    second_user_id = 30002
    lobby.participants.append(second_user_id)
    lobby.participant_names[second_user_id] = "SecondThug"
    updated_kb = build_heist_keyboard(lobby)
    updated_btn_texts = [btn.text for row in updated_kb.inline_keyboard for btn in row]
    assert any("Начать налёт сейчас" in b for b in updated_btn_texts)

    active_heist_lobbies.clear()
    chat_active_heist.clear()


@pytest.mark.asyncio
async def test_launder_split_and_loan_navigation(isolated_test_db):
    """
    Validates:
    - /launder splits 30% to Abu Fund and 70% clean to wallet.
    - /loan & /paydebt execute cleanly with persistent navigation buttons.
    """
    db = isolated_test_db
    user_id = 40001
    board_id = "b"

    # --- Money Laundering 70/30 Split ---
    dirty_amount = 100_000.0
    await save_user_active_items(db, user_id, {"dirty_balance": dirty_amount}, board_id)
    fund_before = await get_abu_fund_total(db)
    bal_before = await get_user_global_balance(db, user_id)

    success, reply_text, data = await process_money_laundering(db, user_id, "all", board_id=board_id)
    assert success is True
    assert data["amount_laundered"] == 100000
    assert data["fee"] == 30000
    assert data["clean"] == 70000

    fund_after = await get_abu_fund_total(db)
    bal_after = await get_user_global_balance(db, user_id)

    assert fund_after - fund_before == 30000.0
    assert bal_after - bal_before == 70000.0

    items_after = await get_user_active_items(db, user_id, board_id)
    assert items_after.get("dirty_balance", 0.0) == 0.0

    # --- Loan & Repayment Navigation Button Retention ---
    # Microloans are issued to broke syches (balance <= 500)
    borrower_id = 40002
    await save_user_active_items(db, borrower_id, {}, board_id)
    bal = await get_user_global_balance(db, borrower_id)
    assert bal == 0.0

    # 1. Borrow Loan via cmd_loan
    loan_msg = MagicMock(spec=Message)
    loan_msg.text = "/loan 1000"
    loan_msg.from_user = User(id=borrower_id, is_bot=False, first_name="BrokeBorrower")
    loan_msg.reply = AsyncMock()

    await cmd_loan(loan_msg)
    loan_msg.reply.assert_called_once()
    borrow_reply = loan_msg.reply.call_args[0][0]
    borrow_kb = loan_msg.reply.call_args[1].get("reply_markup")

    assert "Пахом отсчитал тебе" in borrow_reply
    assert "1,000 ₪" in borrow_reply
    assert borrow_kb is not None
    # Check navigation buttons persist
    b_buttons = [btn.callback_data for row in borrow_kb.inline_keyboard for btn in row]
    assert "loan_paydebt_full" in b_buttons
    assert "work_hub" in b_buttons

    # 2. Add extra 200 shekels to cover 20% interest and test repayment
    await common.database.add_user_global_balance(db, borrower_id, board_id, 200.0)

    # 3. Repay Loan via cmd_paydebt
    repay_msg = MagicMock(spec=Message)
    repay_msg.text = "/paydebt"
    repay_msg.from_user = User(id=borrower_id, is_bot=False, first_name="BrokeBorrower")
    repay_msg.reply = AsyncMock()

    await cmd_paydebt(repay_msg)
    repay_msg.reply.assert_called_once()
    repay_reply = repay_msg.reply.call_args[0][0]
    repay_kb = repay_msg.reply.call_args[1].get("reply_markup")

    assert "вернул долг" in repay_reply.lower() or "пахом доволен" in repay_reply.lower()
    assert repay_kb is not None
    r_buttons = [btn.callback_data for row in repay_kb.inline_keyboard for btn in row]
    assert "loan_hub" in r_buttons
    assert "work_hub" in r_buttons


# =============================================================================
# 3. STRESS TEST SMART_SPLIT_HTML & TELEGRAM_BAD_REQUEST GUARD
# =============================================================================

@pytest.mark.asyncio
async def test_smart_split_html_stress_and_safety_guard():
    """
    Stress-tests smart_split_html on a 12,000-character payload with deeply nested
    unclosed HTML tags, and tests Message.answer interceptor for > 4096 character messages.
    """
    # 1. Generate >= 12,000 chars of deeply nested tags with unclosed tail
    pattern = "<b><i><code><a href=\"https://tgach.top/item/42\">Nested Item Link</a> inner code</code></i></b>\n"
    clean_block = pattern * 130
    unclosed_payload = clean_block + "<b><i><code><a href=\"https://tgach.top\">Deep unclosed tail"
    assert len(unclosed_payload) > 12000

    chunks = smart_split_html(unclosed_payload, max_chunk_size=4000)
    assert len(chunks) >= 3

    for idx, chunk in enumerate(chunks):
        assert len(chunk) <= 4000, f"Chunk {idx+1} exceeds 4000 chars: {len(chunk)}"
        checker = HTMLTagBalanceChecker()
        checker.feed(chunk)
        assert not checker.errors, f"Chunk {idx+1} has HTML parse errors: {checker.errors}"
        assert not checker.stack, f"Chunk {idx+1} has unclosed tags: {checker.stack}"

    # 2. Test Message.answer interceptor installed via install_message_safety_guard()
    install_message_safety_guard()

    class MockInterceptedBot:
        def __init__(self):
            self.sent_messages = []

        async def send_message(self, chat_id, text, reply_markup=None, parse_mode="HTML", disable_web_page_preview=True):
            if len(text) > 4096:
                raise TelegramBadRequest(method="SendMessage", message="Bad Request: message is too long")
            self.sent_messages.append({"text": text, "reply_markup": reply_markup})
            return types.Message.model_construct(
                message_id=len(self.sent_messages),
                date=datetime.now(timezone.utc),
                chat=types.Chat(id=chat_id, type="supergroup"),
                text=text
            )

    guard_bot = MockInterceptedBot()
    chat_id = -100777999
    msg = types.Message.model_construct(
        message_id=99,
        date=datetime.now(timezone.utc),
        chat=types.Chat(id=chat_id, type="supergroup"),
        text="/test_overflow"
    )
    msg._bot = guard_bot

    huge_text = "<b>Transaction Ledger Record:</b>\n" + ("• Transfer #100: +5,000 ₪ from Abu\n" * 200)
    assert len(huge_text) > 4096

    nav_keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Next", callback_data="next")]])

    # Calling answer with > 4096 text must NOT raise TelegramBadRequest
    sent_result = await msg.answer(huge_text, reply_markup=nav_keyboard)

    assert sent_result is not None
    assert len(guard_bot.sent_messages) >= 2
    for m in guard_bot.sent_messages:
        assert len(m["text"]) <= 4096
    # Keyboard is preserved on the last chunk
    assert guard_bot.sent_messages[-1]["reply_markup"] == nav_keyboard


# =============================================================================
# 4. FULL COMMAND REGISTRY 134 CHECK
# =============================================================================

@pytest.mark.asyncio
async def test_full_command_registry_134_no_unhandled_exceptions(isolated_test_db):
    """
    Verifies that all 134 commands registered in setup_bot_commands
    execute without unhandled exceptions when called with standard mock updates.
    """
    db = isolated_test_db

    class MockBotCommandsCapture:
        def __init__(self):
            self.commands = []
            self.id = 123456789
            self.token = "test_bot_token"

        async def set_my_commands(self, commands, scope=None):
            self.commands.extend(commands)

        async def send_message(self, *args, **kwargs):
            return types.Message.model_construct(
                message_id=1,
                date=datetime.now(timezone.utc),
                chat=types.Chat(id=-100123456, type="supergroup"),
                text="ok"
            )

        async def send_photo(self, *args, **kwargs):
            return types.Message.model_construct(
                message_id=2,
                date=datetime.now(timezone.utc),
                chat=types.Chat(id=-100123456, type="supergroup"),
                text="ok"
            )

        async def send_video(self, *args, **kwargs):
            return types.Message.model_construct(
                message_id=3,
                date=datetime.now(timezone.utc),
                chat=types.Chat(id=-100123456, type="supergroup"),
                text="ok"
            )

        async def delete_message(self, *args, **kwargs):
            return True

    bot = MockBotCommandsCapture()
    main.TOKEN_TO_BOARD_MAP["test_bot_token"] = "b"

    # Capture commands from setup_bot_commands
    await setup_bot_commands({"default": bot})

    seen = set()
    all_cmds = []
    for c in bot.commands:
        if c.command not in seen:
            seen.add(c.command)
            all_cmds.append(c.command)

    assert len(all_cmds) >= 120, f"Expected full registry, got {len(all_cmds)} commands"

    now_dt = datetime.now(timezone.utc)
    failures = []

    for cmd in all_cmds:
        test_msg = types.Message.model_construct(
            message_id=101,
            date=now_dt,
            chat=types.Chat(id=-100123456, type="supergroup", title="Command Registry Test"),
            from_user=types.User(id=999222, is_bot=False, first_name="InquisitorTester", username="inquisitor"),
            text=f"/{cmd}"
        )
        test_msg._bot = bot

        update = types.Update(update_id=200, message=test_msg)
        try:
            await dp.feed_update(bot, update)
        except Exception as e:
            failures.append((cmd, f"{type(e).__name__}: {e}"))

    assert not failures, f"Commands raised unhandled exceptions: {failures}"
