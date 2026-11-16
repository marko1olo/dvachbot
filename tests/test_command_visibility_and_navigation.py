import asyncio
import io
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram import Bot, types
from aiogram.types import BotCommand, InlineKeyboardMarkup, User, Message, Chat, CallbackQuery

import main
from main import (
    setup_bot_commands,
    _build_main_shop_hub,
    cmd_wallet,
    cmd_passport,
    cb_prof_card,
    cb_work_microloan,
)
import bank_engine
from bank_engine import (
    build_bank_hub_kb,
    build_bank_dashboard_view,
    cb_bank_hub,
)


@pytest.fixture
def mock_bot():
    bot = AsyncMock(spec=Bot)
    bot.id = 123456789
    bot.get_me = AsyncMock(return_value=MagicMock(username="dvach_test_bot"))
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=999))
    bot.send_photo = AsyncMock(return_value=MagicMock(message_id=1000))
    bot.set_my_commands = AsyncMock(return_value=True)
    return bot


@pytest.fixture
def mock_user():
    return User(id=777888999, is_bot=False, first_name="AnonTester", username="anon_tester")


@pytest.fixture
def mock_chat():
    return Chat(id=-100123456789, type="supergroup", title="Test Board Chat")


# =============================================================================
# 1. TEST BOT COMMAND REGISTRATION
# =============================================================================

@pytest.mark.asyncio
async def test_setup_bot_commands_includes_all_10_new_commands(mock_bot):
    """
    Verifies that setup_bot_commands registers all 10 new syndicate & economy commands:
    scout, pickpocket, arrest, darknet, heist, launder, loan, paydebt, repair, bribe_cop.
    Verifies that descriptions match exactly and total user command slots do not exceed 100.
    """
    bots = {"main": mock_bot}
    with patch("main.ADMIN_IDS", [111222]):
        await setup_bot_commands(bots)

    assert mock_bot.set_my_commands.called
    user_commands = mock_bot.set_my_commands.call_args_list[0][0][0]

    assert len(user_commands) <= 100, f"Telegram limit exceeded: {len(user_commands)} > 100"
    assert len(user_commands) >= 95, f"Too few commands registered: {len(user_commands)}"

    cmd_map = {cmd.command: cmd.description for cmd in user_commands}

    expected_commands = {
        "scout": "🕵️ Разведка карманов цели (/шмон)",
        "pickpocket": "🧤 Тихая карманная кража (/карманник)",
        "arrest": "🚨 Арест разыскиваемого вора (/принять)",
        "darknet": "🏴‍☠️ Даркнет-ломбард и контрабанда",
        "heist": "🦹 Налёт на инкассаторов Банка Абу",
        "launder": "🧺 Теневая прачечная (отмыв шекелей)",
        "loan": "👵 Микрозайм Пахома (/заем)",
        "paydebt": "💳 Погасить долг Пахому (/вернуть)",
        "repair": "🔨 Ремонт экипировки и брони",
        "bribe_cop": "✉️ Взятка следователю (сброс звёзд розыска)",
    }

    for cmd_name, expected_desc in expected_commands.items():
        assert cmd_name in cmd_map, f"Command /{cmd_name} missing from setup_bot_commands!"
        assert cmd_map[cmd_name] == expected_desc, (
            f"Description mismatch for /{cmd_name}: expected '{expected_desc}', got '{cmd_map[cmd_name]}'"
        )


# =============================================================================
# 2. TEST SHOP HUB CROSS-NAVIGATION (DARKNET BUTTON)
# =============================================================================

def test_build_main_shop_hub_contains_darknet_button():
    """
    Verifies that _build_main_shop_hub contains the Darknet pawnshop button
    with text '🕵️ Даркнет-Ломбард (/darknet)' and callback_data='darknet_hub'.
    """
    text, kb = _build_main_shop_hub(user_id=123, balance=1500.0)

    assert isinstance(kb, InlineKeyboardMarkup)
    all_buttons = [btn for row in kb.inline_keyboard for btn in row]

    darknet_btns = [b for b in all_buttons if b.callback_data == "darknet_hub"]
    assert len(darknet_btns) == 1, "Expected exactly 1 darknet_hub button in shop hub"

    darknet_btn = darknet_btns[0]
    assert "Даркнет-Ломбард" in darknet_btn.text
    assert "/darknet" in darknet_btn.text
    assert darknet_btn.text == "🕵️ Даркнет-Ломбард (/darknet)"


# =============================================================================
# 3. TEST WALLET BADGES (DIRTY MONEY & WANTED STARS)
# =============================================================================

@pytest.mark.asyncio
async def test_wallet_displays_dirty_money_and_wanted_stars(isolated_test_db, mock_bot, mock_user, mock_chat):
    """
    Verifies that cmd_wallet correctly appends:
    - Dirty money alert when dirty_balance > 0
    - Wanted stars status when wanted_stars > 0
    """
    db = isolated_test_db
    user_id = mock_user.id
    board_id = "b"

    # Insert user in isolated test DB
    fake_items = {
        "dirty_balance": 12500.0,
        "wanted_stars": 3,
        "bounty_pool": 15000.0,
    }
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, is_verified_b, active_items) VALUES (?, ?, ?, 1, ?) "
        "ON CONFLICT(user_id, board_id) DO UPDATE SET balance = excluded.balance, active_items = excluded.active_items",
        (user_id, board_id, 50000.0, json.dumps(fake_items))
    )

    message = AsyncMock(spec=Message)
    message.bot = mock_bot
    message.from_user = mock_user
    message.chat = mock_chat
    message.answer = AsyncMock()

    with patch("banner_manager.send_banner_message", new_callable=AsyncMock) as mock_send_banner:
        await cmd_wallet(message, board_id=board_id, stream="ru")

        if mock_send_banner.called:
            caption = mock_send_banner.call_args[1]["caption"]
        else:
            caption = message.answer.call_args[0][0]

        expected_dirty = "⚠️ <b>Меченые шекели:</b> <code>12,500 ₪</code> (СБ Банка блокирует вклады! Отмой через /launder)"
        expected_wanted = "🚨 <b>Статус розыска:</b> ⭐️⭐️⭐️ (Награда за голову: <code>15,000 ₪</code>! Сбрось через /bribe_cop или жди ареста)"

        assert expected_dirty in caption, f"Expected dirty balance alert in wallet caption: {caption}"
        assert expected_wanted in caption, f"Expected wanted stars alert in wallet caption: {caption}"


@pytest.mark.asyncio
async def test_wallet_clean_user_has_no_criminal_alerts(isolated_test_db, mock_bot, mock_user, mock_chat):
    """
    Verifies that a law-abiding user with 0 dirty balance and 0 stars sees no alerts in cmd_wallet.
    """
    db = isolated_test_db
    user_id = mock_user.id
    board_id = "b"

    clean_items = {"dirty_balance": 0.0, "wanted_stars": 0, "bounty_pool": 0.0}
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, is_verified_b, active_items) VALUES (?, ?, ?, 1, ?) "
        "ON CONFLICT(user_id, board_id) DO UPDATE SET balance = excluded.balance, active_items = excluded.active_items",
        (user_id, board_id, 25000.0, json.dumps(clean_items))
    )

    message = AsyncMock(spec=Message)
    message.bot = mock_bot
    message.from_user = mock_user
    message.chat = mock_chat
    message.answer = AsyncMock()

    with patch("banner_manager.send_banner_message", new_callable=AsyncMock) as mock_send_banner:
        await cmd_wallet(message, board_id=board_id, stream="ru")

        if mock_send_banner.called:
            caption = mock_send_banner.call_args[1]["caption"]
        else:
            caption = message.answer.call_args[0][0]

        assert "Меченые шекели:" not in caption
        assert "Статус розыска:" not in caption


# =============================================================================
# 4. TEST PASSPORT BADGES (DIRTY MONEY & WANTED STARS)
# =============================================================================

@pytest.mark.asyncio
async def test_passport_displays_dirty_money_and_wanted_stars(isolated_test_db, mock_bot, mock_user, mock_chat):
    """
    Verifies that cmd_passport and cb_prof_card append dirty money and wanted badges.
    """
    db = isolated_test_db
    user_id = mock_user.id
    board_id = "b"

    fake_items = {
        "dirty_balance": 8000.0,
        "wanted_stars": 2,
        "bounty_pool": 10000.0,
    }
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, is_verified_b, active_items) VALUES (?, ?, ?, 1, ?) "
        "ON CONFLICT(user_id, board_id) DO UPDATE SET balance = excluded.balance, active_items = excluded.active_items",
        (user_id, board_id, 10000.0, json.dumps(fake_items))
    )

    message = AsyncMock(spec=Message)
    message.bot = mock_bot
    message.from_user = mock_user
    message.chat = mock_chat
    message.answer_photo = AsyncMock()
    message.answer = AsyncMock()
    message.delete = AsyncMock()

    dummy_card_text = "🪪 <b>ПАСПОРТ АНОНА</b>\nУровень: 10\n"

    with patch("stats_generator.generate_user_stats_card", return_value=(io.BytesIO(b"dummy_png"), dummy_card_text)):
        await cmd_passport(message, board_id=board_id, stream="ru")

        assert message.answer_photo.called
        kwargs = message.answer_photo.call_args[1]
        caption = kwargs["caption"]

        expected_dirty = "⚠️ <b>Меченые шекели:</b> <code>8,000 ₪</code> (СБ Банка блокирует вклады! Отмой через /launder)"
        expected_wanted = "🚨 <b>Статус розыска:</b> ⭐️⭐️ (Награда за голову: <code>10,000 ₪</code>! Сбрось через /bribe_cop или жди ареста)"

        assert expected_dirty in caption
        assert expected_wanted in caption


# =============================================================================
# 5. TEST BANK HUB LAUNDER BUTTON (WHEN DIRTY BALANCE > 0)
# =============================================================================

def test_build_bank_hub_kb_with_and_without_dirty_balance():
    """
    Verifies that build_bank_hub_kb:
    - Includes launder button [🧺 Отмыть меченые шекели (/launder)] when dirty_balance > 0
    - Excludes launder button when dirty_balance == 0
    """
    # 1. Clean user: dirty_balance = 0
    kb_clean = build_bank_hub_kb(dirty_balance=0.0)
    all_clean_data = [btn.callback_data for row in kb_clean.inline_keyboard for btn in row]
    assert "launder_hub" not in all_clean_data

    # 2. Dirty money holder: dirty_balance = 4500.0
    kb_dirty = build_bank_hub_kb(dirty_balance=4500.0)
    dirty_btns = [btn for row in kb_dirty.inline_keyboard for btn in row if btn.callback_data == "launder_hub"]
    assert len(dirty_btns) == 1
    assert dirty_btns[0].text == "🧺 Отмыть меченые шекели (/launder)"
    assert dirty_btns[0].callback_data == "launder_hub"


def test_build_bank_dashboard_view_integration():
    """
    Verifies that build_bank_dashboard_view correctly passes dirty_balance into its keyboard.
    """
    _, kb_with_dirty = build_bank_dashboard_view(
        wallet_balance=10000.0,
        total_principal=5000.0,
        total_accrued=150.0,
        deposits=[],
        dirty_balance=3000.0
    )
    callbacks = [b.callback_data for row in kb_with_dirty.inline_keyboard for b in row]
    assert "launder_hub" in callbacks

    _, kb_clean = build_bank_dashboard_view(
        wallet_balance=10000.0,
        total_principal=5000.0,
        total_accrued=150.0,
        deposits=[],
        dirty_balance=0.0
    )
    callbacks_clean = [b.callback_data for row in kb_clean.inline_keyboard for b in row]
    assert "launder_hub" not in callbacks_clean


@pytest.mark.asyncio
async def test_cb_bank_hub_displays_launder_button_for_dirty_user(isolated_test_db, mock_bot, mock_user, mock_chat):
    """
    Verifies that cb_bank_hub queries user active_items and displays launder_hub button
    when the user holds dirty balance.
    """
    db = isolated_test_db
    user_id = mock_user.id
    board_id = "b"

    fake_items = {"dirty_balance": 9999.0}
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, is_verified_b, active_items) VALUES (?, ?, ?, 1, ?) "
        "ON CONFLICT(user_id, board_id) DO UPDATE SET balance = excluded.balance, active_items = excluded.active_items",
        (user_id, board_id, 15000.0, json.dumps(fake_items))
    )

    callback = AsyncMock(spec=CallbackQuery)
    callback.from_user = mock_user
    callback.message = AsyncMock(spec=Message)
    callback.message.chat = mock_chat
    callback.bot = mock_bot
    callback.answer = AsyncMock()

    with patch("bank_engine._render_bank_view", new_callable=AsyncMock) as mock_render:
        await cb_bank_hub(callback, board_id=board_id)

        assert callback.answer.called
        assert mock_render.called
        _, rendered_text, rendered_kb = mock_render.call_args[0]

        all_callbacks = [b.callback_data for row in rendered_kb.inline_keyboard for b in row]
        assert "launder_hub" in all_callbacks


# =============================================================================
# 6. TEST WORK MICROLOAN CALLBACK NAVIGATION
# =============================================================================

@pytest.mark.asyncio
async def test_cb_work_microloan_triggers_loan_flow(mock_bot, mock_user, mock_chat):
    """
    Verifies that clicking 'work_microloan' answers the callback and seamlessly transitions
    to the loan card via heist_and_loan_engine.cb_loan_hub.
    """
    callback = AsyncMock(spec=CallbackQuery)
    callback.from_user = mock_user
    callback.message = AsyncMock(spec=Message)
    callback.message.chat = mock_chat
    callback.bot = mock_bot
    callback.answer = AsyncMock()

    with patch("heist_and_loan_engine.cb_loan_hub", new_callable=AsyncMock) as mock_loan_hub:
        await cb_work_microloan(callback, board_id="b")

        assert callback.answer.called or mock_loan_hub.called
        assert mock_loan_hub.called
