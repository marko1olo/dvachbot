# -*- coding: utf-8 -*-
"""
tests/test_seamless_menu_transitions.py — Comprehensive Test Suite for
Universal Safe View Renderer / Transition Helper (render_menu_transition)
and Seamless Menu Navigation across DvachBot Telegram Interface.
"""

import inspect
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

from common.bot_helpers import (
    render_menu_transition,
    render_menu_view,
    is_media_message,
    safe_callback_answer,
)
from criminal_syndicate_engine import (
    cb_darknet_refresh,
    cb_darknet_open_shop,
    build_darknet_keyboard,
    build_darknet_menu_text,
)
from heist_and_loan_engine import (
    cb_loan_hub,
    build_loan_keyboard,
    cb_launder_hub,
    build_launder_keyboard,
    save_user_active_items,
)
from main import (
    _build_main_shop_hub,
    cb_work_microloan,
    cb_work_main_hub,
    _render_shop_subview,
)
from bank_engine import (
    _render_bank_view,
    build_bank_hub_kb,
    cb_bank_hub,
)


# =============================================================================
# PART 1: CORE RENDERER TESTS (render_menu_transition / render_menu_view)
# =============================================================================

@pytest.mark.asyncio
async def test_render_menu_view_alias():
    """Verifies that render_menu_view is a direct alias of render_menu_transition."""
    assert render_menu_view is render_menu_transition


@pytest.mark.asyncio
async def test_is_media_message_detection():
    """Verifies media detection across real and mocked message types."""
    assert not is_media_message(None)

    # Plain text message
    text_msg = MagicMock()
    text_msg.photo = None
    text_msg.caption = None
    text_msg.video = None
    text_msg.animation = None
    text_msg.content_type = "text"
    assert not is_media_message(text_msg)

    # Photo message with list of PhotoSize
    photo_msg = MagicMock()
    photo_msg.photo = [MagicMock()]
    assert is_media_message(photo_msg)

    # Message with caption
    caption_msg = MagicMock()
    caption_msg.photo = None
    caption_msg.caption = "Some caption"
    assert is_media_message(caption_msg)

    # Message with video
    video_msg = MagicMock()
    video_msg.photo = None
    video_msg.caption = None
    video_msg.video = "video_file_id"
    assert is_media_message(video_msg)

    # Message with content_type == 'photo'
    ct_photo = MagicMock()
    ct_photo.photo = None
    ct_photo.caption = None
    ct_photo.content_type = "photo"
    assert is_media_message(ct_photo)


@pytest.mark.asyncio
async def test_transition_photo_to_text():
    """
    Photo message -> Text menu transition:
    When current message is a photo/banner and target view cannot be a banner
    (prefer_banner=False), it deletes the photo message and sends a new text message.
    """
    cb = MagicMock(spec=types.CallbackQuery)
    cb.data = "darknet_hub"
    cb.answer = AsyncMock()
    cb.from_user = MagicMock(id=12345)

    mock_msg = MagicMock(spec=types.Message)
    mock_msg.chat = MagicMock(id=-100999)
    mock_msg.photo = [MagicMock()]
    mock_msg.delete = AsyncMock()
    mock_msg.answer = AsyncMock()
    cb.message = mock_msg

    text = "🏴‍☠️ <b>DARKNET SYNDICATE</b>\nТеневой рынок нелегального снаряжения."
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 В магазин", callback_data="darknet_open_shop")]
    ])

    await render_menu_transition(cb, text, kb, prefer_banner=False)

    mock_msg.delete.assert_called_once()
    mock_msg.answer.assert_called_once()
    call_args = mock_msg.answer.call_args
    sent_text = call_args[0][0] if call_args[0] else call_args[1].get("text")
    assert sent_text == text
    cb.answer.assert_called_once()


@pytest.mark.asyncio
async def test_transition_text_to_photo():
    """
    Text message -> Photo menu transition:
    When current message is plain text and target view requests a banner
    (prefer_banner=True), it deletes the text message and sends a banner via send_banner_message.
    """
    cb = MagicMock(spec=types.CallbackQuery)
    cb.data = "darknet_open_shop"
    cb.answer = AsyncMock()
    cb.from_user = MagicMock(id=12345)
    cb.bot = MagicMock()

    mock_msg = MagicMock(spec=types.Message)
    mock_msg.chat = MagicMock(id=-100999)
    mock_msg.photo = None
    mock_msg.caption = None
    mock_msg.delete = AsyncMock()
    cb.message = mock_msg

    text = "🏬 <b>ТОРГОВЫЙ ХАБ «ДВАЧ-ПЛАЗА»</b>\nДобро пожаловать в магазин!"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚔️ Оружие", callback_data="shop_cat_weapons")]
    ])

    mock_send_banner = AsyncMock(return_value=MagicMock())
    with patch("banner_manager.send_banner_message", mock_send_banner):
        await render_menu_transition(cb, text, kb, category="shop", prefer_banner=True)

    mock_msg.delete.assert_called_once()
    mock_send_banner.assert_called_once_with(
        bot=cb.bot,
        chat_id=-100999,
        caption=text,
        reply_markup=kb,
        category="shop",
        parse_mode="HTML",
    )
    cb.answer.assert_called_once()


@pytest.mark.asyncio
async def test_transition_photo_to_photo_short_caption():
    """
    Photo message -> Photo message transition (fits caption <= 1020 chars):
    When both source and target are banners and caption fits in Telegram limit,
    it calls edit_caption directly in place without deleting the message.
    """
    cb = MagicMock(spec=types.CallbackQuery)
    cb.data = "shop_cat_weapons"
    cb.answer = AsyncMock()
    cb.from_user = MagicMock(id=12345)

    mock_msg = MagicMock(spec=types.Message)
    mock_msg.chat = MagicMock(id=-100999)
    mock_msg.photo = [MagicMock()]
    mock_msg.edit_caption = AsyncMock()
    mock_msg.delete = AsyncMock()
    cb.message = mock_msg

    text = "⚔️ <b>ОРУЖЕЙНЫЙ ОТДЕЛ</b>\nВыбирай арсенал для самообороны."
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="shop_main_hub")]
    ])

    await render_menu_transition(cb, text, kb, category="weapons", prefer_banner=True)

    mock_msg.edit_caption.assert_called_once_with(
        caption=text,
        reply_markup=kb,
        parse_mode="HTML",
    )
    mock_msg.delete.assert_not_called()
    cb.answer.assert_called_once()


@pytest.mark.asyncio
async def test_transition_photo_to_photo_caption_overflow():
    """
    Photo message -> Caption overflow protection (caption > 1020 chars):
    Telegram strictly limits photo captions to 1024 characters.
    When caption > 1020, Telegram would crash with MESSAGE_CAPTION_TOO_LONG.
    The helper safely deletes the photo and sends the content as a text message via msg.answer.
    """
    cb = MagicMock(spec=types.CallbackQuery)
    cb.data = "shop_cat_huge"
    cb.answer = AsyncMock()
    cb.from_user = MagicMock(id=12345)
    cb.bot = MagicMock()

    mock_msg = MagicMock(spec=types.Message)
    mock_msg.chat = MagicMock(id=-100999)
    mock_msg.photo = [MagicMock()]
    mock_msg.edit_caption = AsyncMock()
    mock_msg.delete = AsyncMock()
    mock_msg.answer = AsyncMock()
    cb.message = mock_msg

    huge_text = "🏬 <b>БОЛЬШОЙ КАТАЛОГ</b>\n" + ("• Товар со всеми характеристиками и подробным описанием\n" * 35)
    assert len(huge_text) > 1024

    await render_menu_transition(cb, huge_text, None, category="shop", prefer_banner=True)

    mock_msg.edit_caption.assert_not_called()
    mock_msg.delete.assert_called_once()
    mock_msg.answer.assert_called_once()
    call_args = mock_msg.answer.call_args
    sent_text = call_args[0][0] if call_args[0] else call_args[1].get("text")
    assert sent_text == huge_text
    cb.answer.assert_called_once()


@pytest.mark.asyncio
async def test_transition_text_to_text_normal():
    """
    Text message -> Text menu transition:
    Standard edit_text in-place navigation without deleting.
    """
    cb = MagicMock(spec=types.CallbackQuery)
    cb.data = "darknet_refresh"
    cb.answer = AsyncMock()
    cb.from_user = MagicMock(id=12345)

    mock_msg = MagicMock(spec=types.Message)
    mock_msg.chat = MagicMock(id=-100999)
    mock_msg.photo = None
    mock_msg.caption = None
    mock_msg.edit_text = AsyncMock()
    mock_msg.delete = AsyncMock()
    cb.message = mock_msg

    text = "🏴‍☠️ <b>DARKNET</b>: Цены обновлены."
    kb = InlineKeyboardMarkup(inline_keyboard=[])

    await render_menu_transition(cb, text, kb, prefer_banner=False)

    mock_msg.edit_text.assert_called_once_with(
        text=text,
        reply_markup=kb,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    mock_msg.delete.assert_not_called()
    cb.answer.assert_called_once()


@pytest.mark.asyncio
async def test_transition_text_to_text_unmodified_toast():
    """
    Text message -> Text menu transition (Message is not modified):
    When user clicks a refresh or hub button and the view content has not changed,
    Telegram raises TelegramBadRequest: message is not modified.
    The helper must intercept this cleanly and show toast '🔄 Информация актуальна'.
    """
    cb = MagicMock(spec=types.CallbackQuery)
    cb.data = "darknet_refresh"
    cb.answer = AsyncMock()
    cb.from_user = MagicMock(id=12345)

    mock_msg = MagicMock(spec=types.Message)
    mock_msg.chat = MagicMock(id=-100999)
    mock_msg.photo = None
    mock_msg.caption = None
    mock_msg.edit_text = AsyncMock(side_effect=TelegramBadRequest(
        method="editMessageText",
        message="Bad Request: message is not modified: specified new message content and reply markup are exactly the same as a current content and reply markup of the message"
    ))
    cb.message = mock_msg

    text = "Тот же самый неизмененный текст"
    await render_menu_transition(cb, text, None, prefer_banner=False)

    cb.answer.assert_called_once_with("🔄 Информация актуальна")


@pytest.mark.asyncio
async def test_transition_photo_to_photo_unmodified_toast():
    """
    Photo message -> Photo message transition (Message is not modified):
    When edit_caption raises 'message is not modified', shows toast '🔄 Информация актуальна'.
    """
    cb = MagicMock(spec=types.CallbackQuery)
    cb.data = "bank_refresh"
    cb.answer = AsyncMock()
    cb.from_user = MagicMock(id=12345)

    mock_msg = MagicMock(spec=types.Message)
    mock_msg.chat = MagicMock(id=-100999)
    mock_msg.photo = [MagicMock()]
    mock_msg.edit_caption = AsyncMock(side_effect=TelegramBadRequest(
        method="editMessageCaption",
        message="Bad Request: message is not modified: specified new message content and reply markup are exactly the same as a current content and reply markup of the message"
    ))
    cb.message = mock_msg

    text = "Тот же самый неизмененный текст"
    await render_menu_transition(cb, text, None, category="bank", prefer_banner=True)

    cb.answer.assert_called_once_with("🔄 Информация актуальна")


@pytest.mark.asyncio
async def test_transition_inaccessible_message_safety():
    """
    InaccessibleMessage or None handling:
    When Telegram gives an InaccessibleMessage (e.g. user interacted with an old or deleted message),
    render_menu_transition must not crash with AttributeError and should fallback gracefully.
    """
    cb = MagicMock(spec=types.CallbackQuery)
    cb.from_user = MagicMock(id=8888)
    cb.bot = MagicMock()
    cb.bot.send_message = AsyncMock()
    cb.answer = AsyncMock()
    inaccessible = MagicMock(spec=types.InaccessibleMessage)
    inaccessible.chat = MagicMock(id=-100555)
    cb.message = inaccessible

    text = "Текст для недоступного сообщения"
    await render_menu_transition(cb, text, None, prefer_banner=False)

    cb.bot.send_message.assert_called_once()
    cb.answer.assert_called_once()


@pytest.mark.asyncio
async def test_direct_message_target():
    """
    When a types.Message object is passed directly (not CallbackQuery),
    render_menu_transition operates directly on the message without error.
    """
    msg = MagicMock(spec=types.Message)
    msg.chat = MagicMock(id=55555)
    msg.bot = MagicMock()
    msg.photo = None
    msg.caption = None
    msg.delete = AsyncMock()

    mock_send_banner = AsyncMock(return_value=MagicMock())
    with patch("banner_manager.send_banner_message", mock_send_banner):
        await render_menu_transition(msg, "Добро пожаловать!", None, category="shop", prefer_banner=True)

    mock_send_banner.assert_called_once()


# =============================================================================
# PART 2: CROSSLINKS AND BACK BUTTONS NAVIGATION TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_shop_to_darknet_crosslink_and_back(isolated_test_db):
    """
    Verifies full bidirectional navigation between Shop and Darknet:
    1. _build_main_shop_hub provides button with callback_data="darknet_hub".
    2. cb_darknet_refresh opens the darknet menu using safe transition.
    3. build_darknet_keyboard provides button with callback_data="darknet_open_shop".
    4. cb_darknet_open_shop cleanly transitions back to the Shop Hub banner.
    """
    db = isolated_test_db
    user_id = 9001
    await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 5000.0)", (user_id,))
    await db.commit()

    # 1. Shop Hub keyboard has darknet button
    text, kb = _build_main_shop_hub(user_id, 5000.0)
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    darknet_btns = [btn for btn in buttons if btn.callback_data == "darknet_hub"]
    assert len(darknet_btns) == 1, "Shop Hub must contain button with callback_data='darknet_hub'"

    # 2. Clicking darknet_hub transitions to Darknet
    cb_shop = MagicMock(spec=types.CallbackQuery)
    cb_shop.from_user = MagicMock(id=user_id)
    cb_shop.data = "darknet_hub"
    cb_shop.answer = AsyncMock()
    mock_msg = MagicMock(spec=types.Message)
    mock_msg.board_id = "b"
    mock_msg.photo = [MagicMock()]
    mock_msg.delete = AsyncMock()
    mock_msg.answer = AsyncMock()
    cb_shop.message = mock_msg

    with patch("common.db_pool.get_pool", AsyncMock(return_value=db)):
        await cb_darknet_refresh(cb_shop, board_id="b")

    mock_msg.delete.assert_called_once()
    mock_msg.answer.assert_called_once()
    assert "DARKNET" in mock_msg.answer.call_args[0][0]

    # 3. Darknet keyboard has return button to Shop
    darknet_kb = build_darknet_keyboard(5000.0)
    darknet_buttons = [btn for row in darknet_kb.inline_keyboard for btn in row]
    shop_return_btns = [btn for btn in darknet_buttons if btn.callback_data == "darknet_open_shop"]
    assert len(shop_return_btns) == 1, "Darknet must contain button with callback_data='darknet_open_shop'"

    # 4. Clicking darknet_open_shop transitions back to Shop banner
    cb_darknet = MagicMock(spec=types.CallbackQuery)
    cb_darknet.from_user = MagicMock(id=user_id)
    cb_darknet.data = "darknet_open_shop"
    cb_darknet.answer = AsyncMock()
    cb_darknet.bot = MagicMock()
    text_msg = MagicMock(spec=types.Message)
    text_msg.board_id = "b"
    text_msg.chat = MagicMock(id=user_id)
    text_msg.photo = None
    text_msg.caption = None
    text_msg.delete = AsyncMock()
    cb_darknet.message = text_msg

    mock_send_banner = AsyncMock(return_value=MagicMock())
    with patch("common.db_pool.get_pool", AsyncMock(return_value=db)), \
         patch("banner_manager.send_banner_message", mock_send_banner):
        await cb_darknet_open_shop(cb_darknet, board_id="b")

    text_msg.delete.assert_called_once()
    mock_send_banner.assert_called_once()
    assert mock_send_banner.call_args[1]["category"] == "shop"


@pytest.mark.asyncio
async def test_work_to_loan_crosslink_and_back(isolated_test_db):
    """
    Verifies full bidirectional navigation between Work and Loan:
    1. Clicking work_microloan in /work triggers cb_work_microloan which delegates to cb_loan_hub.
    2. Loan card opens cleanly with loan choices.
    3. build_loan_keyboard contains back button [⬅️ Назад на биржу (/work)] with callback_data='work_hub'.
    4. Clicking work_hub triggers cb_work_main_hub which transitions back to Work banner.
    """
    db = isolated_test_db
    user_id = 9002
    await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 100.0)", (user_id,))
    await db.commit()

    # 1. Loan keyboard has back button to work
    loan_kb = build_loan_keyboard()
    loan_buttons = [btn for row in loan_kb.inline_keyboard for btn in row]
    work_back_btns = [btn for btn in loan_buttons if btn.callback_data == "work_hub"]
    assert len(work_back_btns) == 1, "Loan Hub must contain back button with callback_data='work_hub'"
    assert "назад на биржу" in work_back_btns[0].text.lower()

    # 2. cb_work_microloan delegates directly to cb_loan_hub
    cb_work = MagicMock(spec=types.CallbackQuery)
    cb_work.from_user = MagicMock(id=user_id)
    cb_work.data = "work_microloan"
    cb_work.answer = AsyncMock()
    work_msg = MagicMock(spec=types.Message)
    work_msg.chat = MagicMock(id=user_id)
    work_msg.photo = [MagicMock()]
    work_msg.delete = AsyncMock()
    work_msg.answer = AsyncMock()
    cb_work.message = work_msg

    with patch("common.db_pool.get_pool", AsyncMock(return_value=db)):
        await cb_work_microloan(cb_work, board_id="b")

    work_msg.delete.assert_called_once()
    work_msg.answer.assert_called_once()
    assert "БЫСТРОШЕКЕЛЬ" in work_msg.answer.call_args[0][0]

    # 3. cb_work_main_hub transitions back to Work card with banner
    cb_loan = MagicMock(spec=types.CallbackQuery)
    cb_loan.from_user = MagicMock(id=user_id)
    cb_loan.data = "work_hub"
    cb_loan.answer = AsyncMock()
    cb_loan.bot = MagicMock()
    loan_msg = MagicMock(spec=types.Message)
    loan_msg.chat = MagicMock(id=user_id)
    loan_msg.photo = None
    loan_msg.caption = None
    loan_msg.delete = AsyncMock()
    cb_loan.message = loan_msg

    mock_send_banner = AsyncMock(return_value=MagicMock())
    with patch("common.db_pool.get_pool", AsyncMock(return_value=db)), \
         patch("banner_manager.send_banner_message", mock_send_banner):
        await cb_work_main_hub(cb_loan, board_id="b")

    loan_msg.delete.assert_called_once()
    mock_send_banner.assert_called_once()
    assert mock_send_banner.call_args[1]["category"] == "work"


@pytest.mark.asyncio
async def test_bank_to_launder_crosslink_and_back(isolated_test_db):
    """
    Verifies full bidirectional navigation between Bank and Launder:
    1. build_bank_hub_kb with dirty_balance > 0 includes launder_hub button.
    2. cb_launder_hub opens the laundering card cleanly.
    3. build_launder_keyboard contains back button [⬅️ Назад в Банк (/bank)] with callback_data='bank_main_hub'.
    4. cb_bank_hub transitions back to Bank Hub with banner.
    """
    db = isolated_test_db
    user_id = 9003
    await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 500.0)", (user_id,))
    await db.commit()
    # Ensure dirty_balance > 0 so launder_hub processes the request
    await save_user_active_items(db, user_id, {"dirty_balance": 15000.0}, "b")

    # 1. Bank Hub keyboard with dirty_balance > 0 contains launder_hub button
    bank_kb = build_bank_hub_kb(dirty_balance=15000.0)
    bank_buttons = [btn for row in bank_kb.inline_keyboard for btn in row]
    launder_btns = [btn for btn in bank_buttons if btn.callback_data == "launder_hub"]
    assert len(launder_btns) == 1, "Bank Hub must contain launder button when dirty_balance > 0"

    # 2. Launder keyboard has return button to Bank
    launder_kb = build_launder_keyboard()
    launder_buttons = [btn for row in launder_kb.inline_keyboard for btn in row]
    bank_return_btns = [btn for btn in launder_buttons if btn.callback_data == "bank_main_hub"]
    assert len(bank_return_btns) == 1, "Launder keyboard must contain return button with callback_data='bank_main_hub'"
    assert "назад в банк" in bank_return_btns[0].text.lower()

    # 3. Clicking launder_hub transitions to Launder card
    cb_bank = MagicMock(spec=types.CallbackQuery)
    cb_bank.from_user = MagicMock(id=user_id)
    cb_bank.data = "launder_hub"
    cb_bank.answer = AsyncMock()
    bank_msg = MagicMock(spec=types.Message)
    bank_msg.chat = MagicMock(id=user_id)
    bank_msg.photo = [MagicMock()]
    bank_msg.delete = AsyncMock()
    bank_msg.answer = AsyncMock()
    cb_bank.message = bank_msg

    with patch("common.db_pool.get_pool", AsyncMock(return_value=db)):
        await cb_launder_hub(cb_bank)

    bank_msg.delete.assert_called_once()
    bank_msg.answer.assert_called_once()
    assert "ПРАЧЕЧНАЯ" in bank_msg.answer.call_args[0][0]

    # 4. Clicking bank_main_hub transitions back to Bank dashboard
    cb_launder = MagicMock(spec=types.CallbackQuery)
    cb_launder.from_user = MagicMock(id=user_id)
    cb_launder.data = "bank_main_hub"
    cb_launder.answer = AsyncMock()
    cb_launder.bot = MagicMock()
    launder_msg = MagicMock(spec=types.Message)
    launder_msg.chat = MagicMock(id=user_id)
    launder_msg.photo = None
    launder_msg.caption = None
    launder_msg.delete = AsyncMock()
    cb_launder.message = launder_msg

    mock_send_banner = AsyncMock(return_value=MagicMock())
    with patch("common.db_pool.get_pool", AsyncMock(return_value=db)), \
         patch("banner_manager.send_banner_message", mock_send_banner):
        await cb_bank_hub(cb_launder, board_id="b")

    launder_msg.delete.assert_called_once()
    mock_send_banner.assert_called_once()
    assert mock_send_banner.call_args[1]["category"] == "bank"


# =============================================================================
# PART 3: SUBVIEW DELEGATION TESTS (_render_shop_subview & _render_bank_view)
# =============================================================================

@pytest.mark.asyncio
async def test_render_shop_subview_delegates_to_transition_helper():
    """Verifies _render_shop_subview correctly uses render_menu_transition."""
    cb = MagicMock(spec=types.CallbackQuery)
    cb.data = "shop_test"
    cb.answer = AsyncMock()
    cb.bot = MagicMock()
    msg = MagicMock(spec=types.Message)
    msg.chat = MagicMock(id=111)
    msg.photo = [MagicMock()]
    msg.edit_caption = AsyncMock()
    cb.message = msg

    await _render_shop_subview(cb, "Магазин оружия", None, category="weapons")
    msg.edit_caption.assert_called_once()


@pytest.mark.asyncio
async def test_render_bank_view_delegates_to_transition_helper():
    """Verifies _render_bank_view correctly uses render_menu_transition."""
    cb = MagicMock(spec=types.CallbackQuery)
    cb.data = "bank_test"
    cb.answer = AsyncMock()
    cb.bot = MagicMock()
    msg = MagicMock(spec=types.Message)
    msg.chat = MagicMock(id=222)
    msg.photo = [MagicMock()]
    msg.edit_caption = AsyncMock()
    cb.message = msg

    await _render_bank_view(cb, "Банк Абу", None, category="bank")
    msg.edit_caption.assert_called_once()
