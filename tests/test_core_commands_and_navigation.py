import asyncio
import io
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from aiogram import Bot, types
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey

import main
from main import (
    SafeMessageProxy,
    safe_callback_answer,
    ThreadCreateStates,
    cmd_passport,
    cmd_wallet,
    cmd_shop,
    cmd_wardrobe,
    cmd_stats,
    cmd_top,
    cmd_graph,
    cmd_settings,
    cmd_boards,
    cmd_help,
    cmd_create_fsm_entry,
    cmd_cancel_fsm,
    cb_create_thread_confirm,
    cb_create_thread_edit,
    cb_create_thread_cancel,
    cb_create_thread_start,
    process_op_post_text,
    cb_top_switch,
    process_help_menu,
    cb_prof_card,
    cb_prof_dossier,
    cb_prof_wallet,
    cb_prof_shop,
    _render_shop_subview,
    _check_menu_owner,
    generate_statistics_graph,
)


@pytest.fixture
def mock_bot():
    bot = AsyncMock(spec=Bot)
    bot.id = 123456789
    bot.get_me = AsyncMock(return_value=MagicMock(username="dvach_test_bot"))
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=999))
    bot.send_photo = AsyncMock(return_value=MagicMock(message_id=1000))
    return bot


@pytest.fixture
def mock_user():
    return types.User(id=555666777, is_bot=False, first_name="Anon", username="anon555")


@pytest.fixture
def mock_chat():
    return types.Chat(id=-100123456789, type="supergroup", title="Test Board Chat")


@pytest.fixture
def fsm_context(mock_bot, mock_user, mock_chat):
    storage = MemoryStorage()
    key = StorageKey(bot_id=mock_bot.id, chat_id=mock_chat.id, user_id=mock_user.id)
    return FSMContext(storage=storage, key=key)


# =============================================================================
# 1. TEST SAFE_CALLBACK_ANSWER & INACCESSIBLE MESSAGE SAFETY
# =============================================================================

@pytest.mark.asyncio
async def test_safe_callback_answer_normal():
    cb = AsyncMock(spec=types.CallbackQuery)
    cb.answer = AsyncMock()
    result = await safe_callback_answer(cb, "Hello!", show_alert=True)
    assert result is True
    cb.answer.assert_called_once_with("Hello!", show_alert=True)


@pytest.mark.asyncio
async def test_safe_callback_answer_query_too_old():
    cb = AsyncMock(spec=types.CallbackQuery)
    cb.answer = AsyncMock(side_effect=TelegramBadRequest(
        method=MagicMock(),
        message="Bad Request: query is too old and response timeout expired or query id is invalid"
    ))
    # Should not raise exception
    result = await safe_callback_answer(cb, "Hello!")
    assert result is False


@pytest.mark.asyncio
async def test_safe_message_proxy_with_normal_message(mock_bot, mock_user, mock_chat):
    real_msg = AsyncMock(spec=types.Message)
    real_msg.bot = mock_bot
    real_msg.chat = mock_chat
    real_msg.date = MagicMock()
    real_msg.message_id = 42
    real_msg.answer = AsyncMock(return_value=MagicMock(message_id=43))

    proxy = SafeMessageProxy(real_msg, mock_user, bot=mock_bot)
    assert proxy.from_user == mock_user
    assert proxy.message_id == 42

    ans = await proxy.answer("Test reply")
    real_msg.answer.assert_called_once_with("Test reply")
    assert ans.message_id == 43


@pytest.mark.asyncio
async def test_safe_message_proxy_with_inaccessible_message(mock_bot, mock_user, mock_chat):
    inacc_msg = types.InaccessibleMessage(chat=mock_chat, message_id=42, date=0)
    inacc_msg.bot = mock_bot

    proxy = SafeMessageProxy(inacc_msg, mock_user, bot=mock_bot)
    assert proxy.from_user == mock_user
    assert proxy.chat == mock_chat

    # InaccessibleMessage has no answer() method, but SafeMessageProxy must fallback to bot.send_message
    await proxy.answer("Fallback reply")
    mock_bot.send_message.assert_called_once()
    assert mock_bot.send_message.call_args.kwargs['chat_id'] == mock_chat.id
    assert mock_bot.send_message.call_args.kwargs['text'] == "Fallback reply"


@pytest.mark.asyncio
async def test_safe_message_proxy_with_none(mock_bot, mock_user):
    proxy = SafeMessageProxy(None, mock_user, bot=mock_bot)
    assert proxy.from_user == mock_user
    assert proxy.bot == mock_bot

    # Fallback to direct user message
    await proxy.answer("Hello user!")
    mock_bot.send_message.assert_called_once()
    assert mock_bot.send_message.call_args.kwargs['chat_id'] == mock_user.id
    assert mock_bot.send_message.call_args.kwargs['text'] == "Hello user!"


@pytest.mark.asyncio
async def test_render_shop_subview_with_inaccessible_message(mock_bot, mock_user, mock_chat):
    cb = AsyncMock(spec=types.CallbackQuery)
    cb.bot = mock_bot
    cb.from_user = mock_user
    cb.message = types.InaccessibleMessage(chat=mock_chat, message_id=99, date=0)

    kb = types.InlineKeyboardMarkup(inline_keyboard=[])
    # Should not crash with AttributeError
    await _render_shop_subview(cb, "Shop content", kb, category="shop")
    # Must have attempted to deliver via bot
    assert mock_bot.send_message.called or mock_bot.send_photo.called


@pytest.mark.asyncio
async def test_check_menu_owner_safety():
    cb = AsyncMock(spec=types.CallbackQuery)
    cb.message = None
    # None message should return True safely
    assert _check_menu_owner(cb) is True

    inacc = types.InaccessibleMessage(chat=types.Chat(id=1, type="private"), message_id=1, date=0)
    cb.message = inacc
    assert _check_menu_owner(cb) is True


# =============================================================================
# 2. TEST FSM SCENARIOS & THREADCREATIONSTATES
# =============================================================================

@pytest.mark.asyncio
async def test_cmd_create_fsm_entry_prompt_mode(mock_bot, mock_user, mock_chat, fsm_context):
    msg = AsyncMock(spec=types.Message)
    msg.bot = mock_bot
    msg.from_user = mock_user
    msg.chat = mock_chat
    msg.text = "/create"
    msg.caption = None
    msg.answer = AsyncMock()
    msg.delete = AsyncMock()

    # Board 'b' is in THREAD_BOARDS
    await cmd_create_fsm_entry(msg, fsm_context, board_id="b", stream="ru")

    # Should set state to waiting_for_op_post
    state = await fsm_context.get_state()
    assert state == ThreadCreateStates.waiting_for_op_post.state
    msg.answer.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_create_fsm_entry_with_inline_args(mock_bot, mock_user, mock_chat, fsm_context):
    msg = AsyncMock(spec=types.Message)
    msg.bot = mock_bot
    msg.from_user = mock_user
    msg.chat = mock_chat
    msg.text = "/create New Test Thread Title"
    msg.html_text = "/create New Test Thread Title"
    msg.caption = None
    msg.answer = AsyncMock()
    msg.delete = AsyncMock()

    await cmd_create_fsm_entry(msg, fsm_context, board_id="b", stream="ru")

    # When args provided, immediately transitions to waiting_for_confirmation
    state = await fsm_context.get_state()
    assert state == ThreadCreateStates.waiting_for_confirmation.state
    data = await fsm_context.get_data()
    assert "New Test Thread Title" in data.get("op_post_text", "")
    # Check confirmation keyboard contains create, edit, and cancel buttons
    msg.answer.assert_called_once()
    kb = msg.answer.call_args.kwargs.get("reply_markup")
    assert kb is not None
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "create_thread_confirm" in callbacks
    assert "create_thread_edit" in callbacks
    assert "create_thread_cancel" in callbacks


@pytest.mark.asyncio
async def test_cmd_create_fsm_entry_already_in_state(mock_bot, mock_user, mock_chat, fsm_context):
    await fsm_context.set_state(ThreadCreateStates.waiting_for_op_post)

    msg = AsyncMock(spec=types.Message)
    msg.bot = mock_bot
    msg.from_user = mock_user
    msg.chat = mock_chat
    msg.text = "/create"
    msg.caption = None
    msg.answer = AsyncMock()
    msg.delete = AsyncMock()

    await cmd_create_fsm_entry(msg, fsm_context, board_id="b", stream="ru")
    msg.answer.assert_called_once()
    assert "cancel" in msg.answer.call_args.args[0].lower() or "отмена" in msg.answer.call_args.args[0].lower() or "уже" in msg.answer.call_args.args[0].lower()


@pytest.mark.asyncio
async def test_process_op_post_text_transitions_to_confirmation(mock_bot, mock_user, mock_chat, fsm_context):
    await fsm_context.set_state(ThreadCreateStates.waiting_for_op_post)

    msg = AsyncMock(spec=types.Message)
    msg.bot = mock_bot
    msg.from_user = mock_user
    msg.chat = mock_chat
    msg.text = "This is the body of the OP post."
    msg.html_text = "This is the body of the OP post."
    msg.caption = None
    msg.answer = AsyncMock()

    await process_op_post_text(msg, fsm_context, board_id="b", stream="ru")

    state = await fsm_context.get_state()
    assert state == ThreadCreateStates.waiting_for_confirmation.state
    data = await fsm_context.get_data()
    assert data["op_post_text"] == "This is the body of the OP post."
    # Verify cancel button is present
    kb = msg.answer.call_args.kwargs.get("reply_markup")
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "create_thread_cancel" in callbacks


@pytest.mark.asyncio
async def test_cb_create_thread_edit(mock_bot, mock_user, mock_chat, fsm_context):
    await fsm_context.set_state(ThreadCreateStates.waiting_for_confirmation)

    cb = AsyncMock(spec=types.CallbackQuery)
    cb.bot = mock_bot
    cb.from_user = mock_user
    real_msg = AsyncMock(spec=types.Message)
    real_msg.edit_text = AsyncMock()
    cb.message = real_msg
    cb.answer = AsyncMock()

    await cb_create_thread_edit(cb, fsm_context, board_id="b", stream="ru")

    state = await fsm_context.get_state()
    assert state == ThreadCreateStates.waiting_for_op_post.state
    real_msg.edit_text.assert_called_once()


@pytest.mark.asyncio
async def test_cb_create_thread_cancel(mock_bot, mock_user, mock_chat, fsm_context):
    await fsm_context.set_state(ThreadCreateStates.waiting_for_confirmation)

    cb = AsyncMock(spec=types.CallbackQuery)
    cb.bot = mock_bot
    cb.from_user = mock_user
    real_msg = AsyncMock(spec=types.Message)
    real_msg.delete = AsyncMock()
    cb.message = real_msg
    cb.answer = AsyncMock()

    await cb_create_thread_cancel(cb, fsm_context, board_id="b", stream="ru")

    state = await fsm_context.get_state()
    assert state is None
    real_msg.delete.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_cancel_fsm(mock_bot, mock_user, mock_chat, fsm_context):
    await fsm_context.set_state(ThreadCreateStates.waiting_for_op_post)

    msg = AsyncMock(spec=types.Message)
    msg.bot = mock_bot
    msg.from_user = mock_user
    msg.chat = mock_chat
    msg.answer = AsyncMock()
    msg.delete = AsyncMock()

    await cmd_cancel_fsm(msg, fsm_context, board_id="b", stream="ru")

    state = await fsm_context.get_state()
    assert state is None
    msg.answer.assert_called_once()


@pytest.mark.asyncio
async def test_cb_create_thread_confirm_cooldown_clears_state(mock_bot, mock_user, mock_chat, fsm_context):
    """Verifies that now_ts is defined and on cooldown state is cleared without NameError."""
    await fsm_context.set_state(ThreadCreateStates.waiting_for_confirmation)
    await fsm_context.update_data(op_post_text="Test OP post")

    cb = AsyncMock(spec=types.CallbackQuery)
    cb.bot = mock_bot
    cb.from_user = mock_user
    cb.message = AsyncMock(spec=types.Message)
    cb.answer = AsyncMock()

    # Simulate user on cooldown by setting last_thread_creation = now
    main.board_data.setdefault("b", {}).setdefault("user_state", {}).setdefault(mock_user.id, {})["last_thread_creation"] = time.time()

    await cb_create_thread_confirm(cb, fsm_context, board_id="b", stream="ru")

    # State must be cleared, no NameError: now_ts
    state = await fsm_context.get_state()
    assert state is None


# =============================================================================
# 3. TEST CORE COMMANDS ROUTING & EXECUTION
# =============================================================================

@pytest.mark.asyncio
async def test_cmd_passport_execution(mock_bot, mock_user, mock_chat):
    msg = AsyncMock(spec=types.Message)
    msg.bot = mock_bot
    msg.from_user = mock_user
    msg.chat = mock_chat
    msg.answer_photo = AsyncMock()
    msg.answer = AsyncMock()
    msg.delete = AsyncMock()

    # Mock stats card generator to return in-memory dummy PNG
    fake_buf = io.BytesIO(b"\x89PNG\r\n\x1a\nfake_image_data")
    with patch("stats_generator.generate_user_stats_card", return_value=(fake_buf, "<b>Паспорт Анона</b>")):
        await cmd_passport(msg, board_id="b", stream="ru")

    assert msg.answer_photo.called or msg.answer.called


@pytest.mark.asyncio
async def test_cmd_wallet_execution(mock_bot, mock_user, mock_chat):
    msg = AsyncMock(spec=types.Message)
    msg.bot = mock_bot
    msg.from_user = mock_user
    msg.chat = mock_chat
    msg.answer = AsyncMock()
    msg.delete = AsyncMock()

    await cmd_wallet(msg, board_id="b", stream="ru")
    assert msg.answer.called
    assert "КОШЕЛЕК" in msg.answer.call_args.args[0] or "CRYPTO-WALLET" in msg.answer.call_args.args[0]


@pytest.mark.asyncio
async def test_cmd_shop_and_wardrobe_execution(mock_bot, mock_user, mock_chat):
    msg = AsyncMock(spec=types.Message)
    msg.bot = mock_bot
    msg.from_user = mock_user
    msg.chat = mock_chat
    msg.answer = AsyncMock()
    msg.delete = AsyncMock()

    with patch("banner_manager.send_banner_message", new_callable=AsyncMock) as mock_send_banner:
        mock_send_banner.return_value = MagicMock(chat=mock_chat, message_id=123)
        await cmd_shop(msg, board_id="b", stream="ru")
        assert mock_send_banner.called

    with patch("banner_manager.send_banner_message", new_callable=AsyncMock) as mock_send_banner:
        mock_send_banner.return_value = MagicMock(chat=mock_chat, message_id=124)
        await cmd_wardrobe(msg, board_id="b", stream="ru")
        assert mock_send_banner.called


@pytest.mark.asyncio
async def test_cmd_stats_and_top_execution(mock_bot, mock_user, mock_chat):
    msg = AsyncMock(spec=types.Message)
    msg.bot = mock_bot
    msg.from_user = mock_user
    msg.chat = mock_chat
    msg.answer = AsyncMock()
    msg.answer_photo = AsyncMock()
    msg.delete = AsyncMock()

    # cmd_stats with mocked chart generator
    fake_png = b"\x89PNG\r\n\x1a\nfake_stats_chart"
    with patch("main._generate_stats_charts", return_value=[fake_png]):
        # Clear cooldown
        main._stats_cooldown_tracker.clear()
        await cmd_stats(msg, board_id="b", stream="ru")
        assert msg.answer_photo.called or msg.answer.called

    # cmd_top with mocked leaderboard payload
    fake_buf = io.BytesIO(fake_png)
    with patch("leaderboard_card.generate_leaderboard_payload", return_value=(fake_buf, "<b>Топ Лидеров</b>")):
        await cmd_top(msg, board_id="b", stream="ru")
        assert msg.answer_photo.called or msg.answer.called


@pytest.mark.asyncio
async def test_cmd_graph_execution(mock_bot, mock_user, mock_chat):
    msg = AsyncMock(spec=types.Message)
    msg.bot = mock_bot
    msg.from_user = mock_user
    msg.chat = mock_chat
    msg.text = "/graph"
    msg.caption = None
    msg.answer = AsyncMock()
    msg.answer_photo = AsyncMock()
    msg.delete = AsyncMock()

    fake_png = b"\x89PNG\r\n\x1a\nfake_graph"
    with patch("main.generate_statistics_graph", return_value=fake_png):
        await cmd_graph(msg, board_id="b", stream="ru")
        assert msg.answer_photo.called


@pytest.mark.asyncio
async def test_cmd_settings_boards_help_execution(mock_bot, mock_user, mock_chat):
    msg = AsyncMock(spec=types.Message)
    msg.bot = mock_bot
    msg.from_user = mock_user
    msg.chat = mock_chat
    msg.answer = AsyncMock()
    msg.delete = AsyncMock()

    with patch("banner_manager.send_banner_message", new_callable=AsyncMock) as mock_send_banner:
        mock_send_banner.return_value = MagicMock(chat=mock_chat, message_id=125)
        await cmd_settings(msg, board_id="b", stream="ru")
        assert mock_send_banner.called

    with patch("banner_manager.send_banner_message", new_callable=AsyncMock) as mock_send_banner:
        mock_send_banner.return_value = MagicMock(chat=mock_chat, message_id=126)
        await cmd_boards(msg, board_id="b", stream="ru")
        assert mock_send_banner.called

    with patch("banner_manager.send_banner_message", new_callable=AsyncMock) as mock_send_banner:
        mock_send_banner.return_value = MagicMock(chat=mock_chat, message_id=127)
        await cmd_help(msg, board_id="b", stream="ru")
        assert mock_send_banner.called


# =============================================================================
# 4. TEST CALLBACK NAVIGATION & INACCESSIBLE MESSAGE TOLERANCE
# =============================================================================

@pytest.mark.asyncio
async def test_cb_top_switch_with_inaccessible_message(mock_bot, mock_user, mock_chat):
    cb = AsyncMock(spec=types.CallbackQuery)
    cb.bot = mock_bot
    cb.from_user = mock_user
    cb.data = "top_switch_balance"
    cb.message = types.InaccessibleMessage(chat=mock_chat, message_id=888, date=0)
    cb.answer = AsyncMock()

    fake_buf = io.BytesIO(b"\x89PNG\r\n\x1a\nfake_top")
    with patch("leaderboard_card.generate_leaderboard_payload", return_value=(fake_buf, "<b>Топ</b>")):
        # Must not raise AttributeError
        await cb_top_switch(cb, board_id="b")
        mock_bot.send_photo.assert_called_once()


@pytest.mark.asyncio
async def test_process_help_menu_with_inaccessible_message(mock_bot, mock_user, mock_chat):
    cb = AsyncMock(spec=types.CallbackQuery)
    cb.bot = mock_bot
    cb.from_user = mock_user
    cb.data = "help:chat"
    cb.message = types.InaccessibleMessage(chat=mock_chat, message_id=889, date=0)
    cb.answer = AsyncMock()

    # Must not raise AttributeError
    with patch("banner_manager.send_banner_message", new_callable=AsyncMock) as mock_banner:
        await process_help_menu(cb, board_id="b", stream="ru")
        assert mock_banner.called or mock_bot.send_message.called


@pytest.mark.asyncio
async def test_cb_prof_actions_proxy_safety(mock_bot, mock_user, mock_chat):
    cb = AsyncMock(spec=types.CallbackQuery)
    cb.bot = mock_bot
    cb.from_user = mock_user
    cb.message = types.InaccessibleMessage(chat=mock_chat, message_id=890, date=0)
    cb.answer = AsyncMock()

    with patch("main.cmd_wallet", new_callable=AsyncMock) as mock_wallet:
        await cb_prof_wallet(cb, board_id="b", stream="ru")
        assert mock_wallet.called
        # Check proxy passed has bot and from_user
        proxy_arg = mock_wallet.call_args.args[0]
        assert proxy_arg.from_user == mock_user
        assert proxy_arg.bot == mock_bot

    with patch("main.cmd_shop", new_callable=AsyncMock) as mock_shop:
        await cb_prof_shop(cb, board_id="b", stream="ru")
        assert mock_shop.called

    with patch("main.cmd_dossier", new_callable=AsyncMock) as mock_dossier:
        await cb_prof_dossier(cb, board_id="b")
        assert mock_dossier.called
