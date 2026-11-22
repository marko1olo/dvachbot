# -*- coding: utf-8 -*-
"""
tests/test_bot_ui_ux_navigation.py — Telegram UI/UX & Callback Navigation Inquisitor Test Suite

Verifies:
1. Guaranteed callback_query.answer() under all conditions (normal, early returns, exceptions).
2. Resilience against TelegramBadRequest: "message is not modified".
3. Correct HTML escaping of special characters (<, >, &, _) in usernames, titles, prefixes, preventing entity parse crashes.
4. Navigation and pagination integrity across all inline keyboards and menus (no loops, valid callbacks).
5. User-friendly alerts on expired sessions or invalid actions.
"""

import asyncio
import html
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from aiogram import Bot, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from common.bot_helpers import safe_callback_answer, render_menu_transition
from main import (
    CallbackAnswerGuardMiddleware,
    _build_main_shop_hub,
    _build_inventory_content,
    _build_dressing_room_content,
    _format_ledger_view,
    get_personal_menu_keyboard,
    cb_top_switch,
    cb_set_stream,
    cb_abu_fund_refresh,
    cb_duel_accept,
    cb_duel_decline,
    cb_drop_handler,
    cb_create_thread_confirm,
    cb_create_thread_edit,
    cq_threads_page,
    cq_view_thread,
    cb_dopros_action,
    cb_prof_ledger,
    cb_wardrobe_page,
)
import avatar_generator
import stats_generator


# =============================================================================
# FIXTURES & HELPERS
# =============================================================================

def make_mock_callback(
    callback_id: str = "test_cb_123",
    data: str = "test_action",
    user_id: int = 12345,
    chat_id: int = -1001234567,
    message_id: int = 999,
    is_photo: bool = False,
    caption: str = None,
    text: str = "Original text"
) -> MagicMock:
    """Creates a fully mocked aiogram CallbackQuery with tracking."""
    cb = MagicMock(spec=types.CallbackQuery)
    cb.id = callback_id
    cb.data = data
    cb._answered = False

    user = MagicMock(spec=types.User)
    user.id = user_id
    user.is_bot = False
    user.first_name = "Ivan"
    user.username = "ivan_test"
    cb.from_user = user

    bot = MagicMock(spec=Bot)
    bot.send_message = AsyncMock()
    bot.send_photo = AsyncMock()
    bot.delete_message = AsyncMock()
    cb.bot = bot

    msg = MagicMock(spec=types.Message)
    msg.message_id = message_id
    msg.bot = bot
    chat = MagicMock(spec=types.Chat)
    chat.id = chat_id
    chat.type = "supergroup"
    msg.chat = chat
    msg.edit_text = AsyncMock()
    msg.edit_caption = AsyncMock()
    msg.edit_media = AsyncMock()
    msg.delete = AsyncMock()
    msg.answer = AsyncMock()

    if is_photo:
        msg.photo = [MagicMock()]
        msg.caption = caption or text
        msg.text = None
    else:
        msg.photo = None
        msg.caption = None
        msg.text = text

    cb.message = msg

    # Tracking async answer
    async def mock_answer(*args, **kwargs):
        setattr(cb, "_answered", True)
        return True

    cb.answer = AsyncMock(side_effect=mock_answer)
    return cb


# =============================================================================
# PART 1: MANDATORY ANSWER() AND GUARD MIDDLEWARE TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_guard_middleware_answers_on_normal_completion():
    """Middleware ensures safe_callback_answer is called upon normal handler return."""
    mw = CallbackAnswerGuardMiddleware()
    cb = make_mock_callback()

    async def dummy_handler(event, data):
        return "done"

    res = await mw(dummy_handler, cb, {})
    assert res == "done"
    assert cb._answered is True
    assert cb.answer.called


@pytest.mark.asyncio
async def test_guard_middleware_answers_on_early_return():
    """Middleware ensures safe_callback_answer is called when handler returns early without answer."""
    mw = CallbackAnswerGuardMiddleware()
    cb = make_mock_callback(data="test_action_early")

    async def early_return_handler(event, data):
        # Handler exits early without calling answer()
        return None

    await mw(early_return_handler, cb, {})
    assert cb._answered is True
    assert cb.answer.called


@pytest.mark.asyncio
async def test_guard_middleware_answers_on_unhandled_exception():
    """Middleware ensures safe_callback_answer is called even if handler raises an exception."""
    mw = CallbackAnswerGuardMiddleware()
    cb = make_mock_callback(data="test_action_crash")

    async def crashing_handler(event, data):
        raise RuntimeError("Simulated unhandled exception in handler!")

    with pytest.raises(RuntimeError):
        await mw(crashing_handler, cb, {})

    # Even after crash, the callback MUST have been answered in finally block
    assert cb._answered is True
    assert cb.answer.called


@pytest.mark.asyncio
async def test_safe_callback_answer_idempotent():
    """safe_callback_answer does not send duplicate blank answers if already answered."""
    cb = make_mock_callback()
    
    # First answer
    res1 = await safe_callback_answer(cb)
    assert res1 is True
    assert cb.answer.call_count == 1

    # Second answer without toast - should be skipped
    res2 = await safe_callback_answer(cb)
    assert res2 is True
    assert cb.answer.call_count == 1  # Not called again


@pytest.mark.asyncio
async def test_safe_callback_answer_truncation():
    """safe_callback_answer truncates messages > 195 characters to prevent Telegram API errors."""
    cb = make_mock_callback()
    long_toast = "A" * 300

    await safe_callback_answer(cb, long_toast)
    called_args, _ = cb.answer.call_args
    assert len(called_args[0]) <= 195
    assert called_args[0].endswith("...")


@pytest.mark.asyncio
async def test_safe_callback_answer_suppresses_bad_request():
    """safe_callback_answer gracefully suppresses TelegramBadRequest (e.g. query expired)."""
    cb = make_mock_callback()
    cb.answer = AsyncMock(side_effect=TelegramBadRequest(method="answerCallbackQuery", message="query is too old"))

    # Should not raise exception
    res = await safe_callback_answer(cb, "Hello")
    assert res is False


# =============================================================================
# PART 2: RESILIENCE TO "MESSAGE IS NOT MODIFIED"
# =============================================================================

@pytest.mark.asyncio
async def test_top_switch_message_not_modified_toast():
    """cb_top_switch catches 'message is not modified' and informs user that info is current."""
    cb = make_mock_callback(data="top_switch_balance")
    # Simulate TelegramBadRequest: message is not modified when editing media
    cb.message.photo = [MagicMock()]
    cb.message.edit_media = AsyncMock(
        side_effect=TelegramBadRequest(method="editMessageMedia", message="Bad Request: message is not modified: specified new message content and reply markup are exactly the same")
    )

    with patch("main.get_pool", AsyncMock()), \
         patch("main._MENU_MESSAGE_OWNERS", {}), \
         patch("main.get_leaderboard_keyboard", return_value=InlineKeyboardMarkup(inline_keyboard=[])), \
         patch("leaderboard_card.generate_leaderboard_payload", return_value=(MagicMock(), "Top caption")):
        await cb_top_switch(cb, board_id="b")

    # Verify callback answered with "Информация актуальна" instead of generic error
    assert cb.answer.called
    called_args = cb.answer.call_args[0]
    assert "Информация актуальна" in called_args[0] or "актуальна" in called_args[0]


@pytest.mark.asyncio
async def test_set_stream_message_not_modified_resilience():
    """cb_set_stream gracefully catches 'message is not modified' without crashing."""
    cb = make_mock_callback(data="set_stream_ru")
    cb.message.edit_text = AsyncMock(
        side_effect=TelegramBadRequest(method="editMessageText", message="Bad Request: message is not modified")
    )

    with patch("main.set_user_stream", AsyncMock()), \
         patch("main.board_data", {"b": {"users": {"active": {12345}}, "user_settings": {}}}):
        await cb_set_stream(cb, board_id="b")

    # Message was safely answered
    assert cb._answered is True


@pytest.mark.asyncio
async def test_abu_fund_refresh_message_not_modified_resilience():
    """cb_abu_fund_refresh catches edit exceptions and still provides status update toast."""
    cb = make_mock_callback(data="abu_fund_refresh")
    cb.message.edit_text = AsyncMock(
        side_effect=TelegramBadRequest(method="editMessageText", message="Bad Request: message is not modified")
    )

    with patch("main.get_pool", AsyncMock()), \
         patch("main.get_abu_fund_total", AsyncMock(return_value=50000.0)), \
         patch("main.format_abu_fund_dashboard", return_value="Fund dashboard"):
        await cb_abu_fund_refresh(cb, board_id="b")

    assert cb._answered is True
    called_args = cb.answer.call_args[0]
    assert "Казны Абу обновлен" in called_args[0]


@pytest.mark.asyncio
async def test_render_menu_transition_handles_not_modified():
    """render_menu_transition catches not modified and shows 'Информация актуальна'."""
    cb = make_mock_callback(is_photo=False, text="Old Text")
    cb.message.edit_text = AsyncMock(
        side_effect=TelegramBadRequest(method="editMessageText", message="Bad Request: message is not modified")
    )

    await render_menu_transition(cb, "Old Text", reply_markup=None, prefer_banner=False)

    assert cb._answered is True
    called_args = cb.answer.call_args[0]
    assert "Информация актуальна" in called_args[0]


# =============================================================================
# PART 3: HTML / MARKDOWN ESCAPING OF SPECIAL CHARACTERS
# =============================================================================

@pytest.mark.asyncio
async def test_inventory_prefix_escaping_injection_protection():
    """_build_inventory_content escapes custom prefixes containing HTML tags."""
    evil_prefix = "<script>alert('pwned')</script> & <b>bold</b>"
    user_id = 99999

    mock_db = MagicMock()
    mock_cursor = AsyncMock()
    # Return prefix with dangerous HTML characters
    mock_cursor.fetchone = AsyncMock(return_value=(evil_prefix, 9999999999, 0))
    mock_db.execute.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
    mock_db.execute.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch("main.get_pool", AsyncMock(return_value=mock_db)), \
         patch("main.get_user_global_balance", AsyncMock(return_value=100.0)), \
         patch("main._get_user_active_items", AsyncMock(return_value={})):
        text, kb = await _build_inventory_content(user_id, "b")

    # Raw tag <script> must NOT appear in output; escaped version &lt;script&gt; must appear
    assert "<script>" not in text
    assert "&lt;script&gt;" in text
    assert "&amp;" in text


def test_avatar_html_card_escaping():
    """avatar_generator.build_character_html_card escapes dangerous custom prefixes and anon IDs."""
    evil_prefix = "<evil_tag> && Hacker"
    evil_anon = "<anon>&bad"

    card = avatar_generator.build_character_html_card(
        user_id=123,
        anon_id=evil_anon,
        balance=1000.0,
        posts_count=50,
        active_items={},
        custom_prefix=evil_prefix
    )

    assert "<evil_tag>" not in card
    assert "&lt;evil_tag&gt;" in card
    assert "<anon>" not in card
    assert "&lt;anon&gt;" in card


def test_stats_generator_report_escaping():
    """stats_generator._format_text_report escapes schizo_name, role_name, custom_prefix."""
    data = MagicMock()
    data.schizo_name = "User <One>"
    data.role_name = "Master & Commander"
    data.custom_prefix = "<VIP_KING>"
    data.board_id = "b"
    data.duel_wins = 5
    data.duel_losses = 2
    data.rank = 1
    data.total_users = 100
    data.posts_count = 10
    data.rx_received = 5
    data.approval_pct = 90
    data.rx_given = 2
    data.balance = 500
    data.mutes_count = 0
    data.cringe_factor = 10
    data.chronotype = "Дневной"
    data.slang_comment = "Норм"

    with patch("wardrobe_engine.get_wardrobe_total_stats", return_value={}), \
         patch("wardrobe_engine.get_active_set_bonuses", return_value=[]):
        report = stats_generator._format_text_report(data)

    assert "<One>" not in report
    assert "&lt;One&gt;" in report
    assert "<VIP_KING>" not in report
    assert "&lt;VIP_KING&gt;" in report
    assert "Master &amp; Commander" in report


# =============================================================================
# PART 4: NAVIGATION & PAGINATION INTEGRITY TESTS
# =============================================================================

def test_main_shop_hub_navigation_buttons():
    """_build_main_shop_hub provides valid callbacks to sub-categories without dead ends."""
    text, kb = _build_main_shop_hub(user_id=123, balance=500.0)
    assert isinstance(kb, InlineKeyboardMarkup)

    all_callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row if btn.callback_data]

    # Verify presence of all key hubs and categories
    assert "shop_cat_weapons" in all_callbacks
    assert "shop_cat_clothes" in all_callbacks
    assert "shop_cat_pharma" in all_callbacks
    assert "shop_cat_lootbox" in all_callbacks
    assert "shop_cat_color" in all_callbacks
    assert "avatar_view" in all_callbacks
    assert "work_hub" in all_callbacks


def test_dressing_room_pagination_buttons():
    """_build_dressing_room_content correctly generates pagination and back buttons."""
    # Active items with 8 real clothing items from CLOTHING_CATALOG (owned and permanent)
    catalog_keys = [
        'hat_tinfoil', 'hat_bag', 'hat_crown', 'hat_cat_ears',
        'hat_helmet', 'hat_tophat', 'hat_golden_foil', 'hat_cyber_ushanka'
    ]
    items = {}
    for k in catalog_keys:
        items[f"owned_{k}"] = True
        items[f"{k}_is_permanent"] = True

    text, kb = _build_dressing_room_content(user_id=123, balance=1000.0, active_items=items, page=1)
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row if btn.callback_data]

    # Must contain shop return button
    assert "shop_main_hub" in callbacks
    assert "avatar_view" in callbacks

    # Check page button
    page_buttons = [c for c in callbacks if c.startswith("wardrobe_page_")]
    assert len(page_buttons) >= 1


def test_ledger_pagination_buttons():
    """_format_ledger_view generates page controls and clean return button to passport."""
    txs = [{"timestamp": 1700000000, "amount": 100, "category": "work", "description": "Смена"}]
    summary = {"total_ops": 25, "total_earned": 500, "total_spent": 100}

    text, kb = _format_ledger_view(user_id=123, balance=400.0, transactions=txs, summary=summary, offset=0)
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row if btn.callback_data]

    # Back to passport
    assert "prof_card" in callbacks
    # Return to shop and work
    assert "shop_main_hub" in callbacks
    assert "work_main_hub" in callbacks
    # Next page button for offset 10
    assert "prof_ledger:10" in callbacks


def test_personal_settings_menu_navigation():
    """get_personal_menu_keyboard contains clear toggle actions and return to main menu."""
    with patch("main.board_data", {"b": {"user_settings": {}}}):
        text, kb = get_personal_menu_keyboard(board_id="b", user_id=123, stream="ru")

    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row if btn.callback_data]

    assert "pers_nsfw_toggle" in callbacks
    assert "pers_ai_toggle" in callbacks
    assert "pers_isolation_toggle" in callbacks
    assert "pers_lang_switch" in callbacks
    assert "menu_main" in callbacks  # Back button to main menu


# =============================================================================
# PART 5: EXPIRED SESSIONS & OUTDATED BUTTON ALERTS
# =============================================================================

@pytest.mark.asyncio
async def test_duel_expired_session_alerts():
    """cb_duel_accept and cb_duel_decline alert user when board_id or session is missing."""
    cb = make_mock_callback()

    await cb_duel_accept(cb, board_id=None)
    assert cb.answer.called
    called_args, called_kwargs = cb.answer.call_args
    assert "устарела" in called_args[0] or "недоступен" in called_args[0]
    assert called_kwargs.get("show_alert") is True

    cb2 = make_mock_callback()
    await cb_duel_decline(cb2, board_id=None)
    assert cb2.answer.called
    called_args2, called_kwargs2 = cb2.answer.call_args
    assert "устарела" in called_args2[0] or "недоступен" in called_args2[0]
    assert called_kwargs2.get("show_alert") is True


@pytest.mark.asyncio
async def test_drop_handler_expired_alert():
    """cb_drop_handler alerts user if board_id is missing or session expired."""
    cb = make_mock_callback()
    await cb_drop_handler(cb, board_id=None)

    assert cb.answer.called
    called_args, called_kwargs = cb.answer.call_args
    assert "недоступен" in called_args[0] or "устарел" in called_args[0]
    assert called_kwargs.get("show_alert") is True


@pytest.mark.asyncio
async def test_thread_expired_session_alerts():
    """cb_create_thread_confirm and cq_threads_page provide explicit alerts on invalid board."""
    cb = make_mock_callback()
    state = MagicMock()
    await cb_create_thread_confirm(cb, state=state, board_id=None)

    assert cb.answer.called
    called_args, called_kwargs = cb.answer.call_args
    assert "устарела" in called_args[0]
    assert called_kwargs.get("show_alert") is True

    cb2 = make_mock_callback()
    await cq_threads_page(cb2, board_id=None)
    assert cb2.answer.called
    called_args2, called_kwargs2 = cb2.answer.call_args
    assert "не поддерживает" in called_args2[0]
    assert called_kwargs2.get("show_alert") is True


@pytest.mark.asyncio
async def test_dopros_malformed_data_alert():
    """cb_dopros_action alerts user on malformed data rather than silent death."""
    cb = make_mock_callback(data="invalid_dopros_data_without_colon")
    await cb_dopros_action(cb, board_id="b")

    assert cb.answer.called
    called_args, called_kwargs = cb.answer.call_args
    assert "Неверный формат" in called_args[0]
    assert called_kwargs.get("show_alert") is True


@pytest.mark.asyncio
async def test_drop_claim_escaping_and_not_modified():
    """cb_drop_handler safely escapes malicious donor/claimer names and handles not modified."""
    cb = make_mock_callback(data="drop:claim:drop_123", is_photo=True, caption="Old Drop")
    cb.message.edit_caption = AsyncMock(
        side_effect=TelegramBadRequest(method="editMessageCaption", message="Bad Request: message is not modified")
    )

    mock_drop = MagicMock()
    mock_drop.status = "claimed"
    mock_drop.donor_name = "<evil_donor> & co"
    mock_drop.claimed_name = "<evil_claimer>"
    mock_drop.amount = 1000

    with patch("main.get_pool", AsyncMock()), \
         patch("drop_engine.claim_money_drop", AsyncMock(return_value=(False, "Уже забран", mock_drop))):
        await cb_drop_handler(cb, board_id="b")

    assert cb._answered is True
    # Verify edit_caption was called with escaped strings
    assert cb.message.edit_caption.called
    call_caption = cb.message.edit_caption.call_args[1].get("caption", "")
    assert "<evil_donor>" not in call_caption
    assert "&lt;evil_donor&gt;" in call_caption
    assert "<evil_claimer>" not in call_caption
    assert "&lt;evil_claimer&gt;" in call_caption
