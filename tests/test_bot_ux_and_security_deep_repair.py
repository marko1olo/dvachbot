# -*- coding: utf-8 -*-
"""
tests/test_bot_ux_and_security_deep_repair.py
Redteam 2 Inquisitor Test Suite: Bot UX, Command Scopes, and Session Security Deep Repair.

Covers:
1. Bot command scopes separation:
   - BotCommandScopeAllPrivateChats (full personal list <= 100)
   - BotCommandScopeAllGroupChats (compact public list 15-20 commands)
   - BotCommandScopeAllChatAdministrators (group moderation commands)
   - BotCommandScopeDefault fallback & BotCommandScopeChat for ADMIN_IDS.
2. Token leakage prevention in public groups:
   - cmd_token in group chat suppresses token and sends warning + [🔑 Получить токен в ЛС] deeplink.
   - Quick menu action="token" in group chat suppresses token and sends warning + deeplink.
   - cmd_start with "token" payload seamlessly routes to token generation in private chat.
3. Anti-Session-Hijacking in group chats:
   - common.bot_helpers: check_menu_owner and record_menu_owner logic across private vs group chats.
   - bank_engine callbacks (hub, refresh, deposit, withdraw) reject stranger with:
     "⛔ Это чужое меню! Открой своё через команду".
   - wardrobe callbacks (dressing room, page, equip, unequip, repair_all) reject stranger with:
     "⛔ Это чужое меню! Открой своё через команду".
   - Legitimate owners are permitted in both groups and PM.
4. Navigation UX cleanups:
   - Elimination of duplicate [◀️ Назад] and [⚡ Главное меню] on the same row in market, casino, and auction engines.
   - market_engine catalog-to-lot and lot-to-catalog roundtrip preserves category, sort_order, and page.
"""

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram import Bot, types
from aiogram.types import (
    BotCommandScopeAllChatAdministrators,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    Chat,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    User,
)

import auction_engine
import casino_engine
from common.bot_helpers import (
    _MENU_MESSAGE_OWNERS,
    check_menu_owner,
    get_menu_owner,
    record_menu_owner,
)
import common.config
from common.db_pool import get_pool
import main
from main import (
    cmd_start,
    cmd_token,
    cmd_wardrobe,
    setup_bot_commands,
)
import market_engine
from market_engine import (
    build_market_catalog_kb,
    build_market_main_menu_kb,
    cb_market_lot,
)
import wardrobe_engine


@pytest.fixture
def mock_bot():
    bot = AsyncMock(spec=Bot)
    bot.id = 777000111
    bot.token = "123456:TEST_TOKEN_FOR_MOCK"
    bot_user = MagicMock(spec=User)
    bot_user.id = 777000111
    bot_user.is_bot = True
    bot_user.username = "test_dvach_bot"
    bot.get_me = AsyncMock(return_value=bot_user)
    return bot


# =============================================================================
# 1. BOT COMMAND SCOPES TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_setup_bot_commands_scopes_separation(mock_bot):
    """
    Verifies that setup_bot_commands properly registers distinct command sets across
    AllPrivateChats, AllGroupChats, and AllChatAdministrators scopes.
    """
    bots = {"b": mock_bot}
    with patch.object(common.config, "ADMIN_IDS", [999001]):
        await setup_bot_commands(bots)

    # Inspect all calls to set_my_commands
    calls = mock_bot.set_my_commands.call_args_list
    assert len(calls) >= 4, f"Expected at least 4 set_my_commands calls, got {len(calls)}"

    scopes_registered = {}
    for call in calls:
        cmds = call.args[0] if call.args else call.kwargs.get("commands", [])
        scope = call.kwargs.get("scope") or (call.args[1] if len(call.args) > 1 else None)
        scope_type = type(scope)
        scopes_registered[scope_type] = cmds

    # 1. AllPrivateChats
    assert BotCommandScopeAllPrivateChats in scopes_registered
    private_cmds = scopes_registered[BotCommandScopeAllPrivateChats]
    assert len(private_cmds) <= 100
    private_names = {c.command for c in private_cmds}
    assert "start" in private_names
    assert "help" in private_names
    assert "balance" in private_names
    assert "wardrobe" in private_names

    # 2. AllGroupChats (15-20 compact public commands)
    assert BotCommandScopeAllGroupChats in scopes_registered
    group_cmds = scopes_registered[BotCommandScopeAllGroupChats]
    assert 15 <= len(group_cmds) <= 20, f"Group commands count {len(group_cmds)} out of range [15, 20]"
    group_names = {c.command for c in group_cmds}
    for required_cmd in ["help", "balance", "pay", "rob", "duel", "summarize", "boards", "report"]:
        assert required_cmd in group_names, f"Required group command '{required_cmd}' missing from group scope"

    # 3. AllChatAdministrators (moderation tools)
    assert BotCommandScopeAllChatAdministrators in scopes_registered
    admin_cmds = scopes_registered[BotCommandScopeAllChatAdministrators]
    admin_names = {c.command for c in admin_cmds}
    for mod_cmd in ["ban", "mute", "unmute", "del", "wipe", "pin", "lockdown"]:
        assert mod_cmd in admin_names, f"Moderation command '{mod_cmd}' missing from admin scope"

    # 4. Fallback default
    assert BotCommandScopeDefault in scopes_registered


# =============================================================================
# 2. TOKEN LEAKAGE PREVENTION IN PUBLIC GROUPS
# =============================================================================

@pytest.mark.asyncio
async def test_cmd_token_in_public_group_suppresses_token(mock_bot, isolated_test_db):
    """
    In a public group (group/supergroup), /token MUST NOT leak the token into the chat.
    Instead, it must send a security warning and a button with start=token deep link.
    """
    user_id = 444111222
    group_chat = MagicMock(spec=Chat)
    group_chat.id = -1001234567890
    group_chat.type = "supergroup"

    msg = MagicMock(spec=Message)
    msg.chat = group_chat
    msg.from_user = MagicMock(spec=User, id=user_id, username="anon_user")
    msg.bot = mock_bot
    msg.text = "/token"
    msg.answer = AsyncMock()
    msg.delete = AsyncMock()

    await cmd_token(msg, board_id="b", stream="ru")

    assert msg.answer.called
    sent_text = msg.answer.call_args_list[0].args[0]
    sent_kb = msg.answer.call_args_list[0].kwargs.get("reply_markup")

    # Verify no raw token is leaked
    assert "Your personal token" not in sent_text
    assert "Ваш токен:" not in sent_text
    assert "<code>" not in sent_text or "tgach.top" not in sent_text

    # Verify warning and deep link button
    assert "Безопасность" in sent_text or "Security" in sent_text
    assert sent_kb is not None
    assert len(sent_kb.inline_keyboard) > 0
    btn = sent_kb.inline_keyboard[0][0]
    assert "Получить токен в ЛС" in btn.text
    assert "start=token" in btn.url
    assert "t.me/test_dvach_bot?start=token" in btn.url


@pytest.mark.asyncio
async def test_cmd_token_in_private_chat_issues_token(mock_bot, isolated_test_db):
    """
    In a private chat, /token should issue the user token normally.
    """
    user_id = 444111333
    priv_chat = MagicMock(spec=Chat)
    priv_chat.id = user_id
    priv_chat.type = "private"

    msg = MagicMock(spec=Message)
    msg.chat = priv_chat
    msg.from_user = MagicMock(spec=User, id=user_id, username="anon_user")
    msg.bot = mock_bot
    msg.text = "/token"
    msg.answer = AsyncMock()
    msg.delete = AsyncMock()

    await cmd_token(msg, board_id="b", stream="ru")

    assert msg.answer.call_count >= 2
    full_output = " ".join([c.args[0] for c in msg.answer.call_args_list if c.args])
    assert "Ваш токен для входа на сайт ТГАЧа" in full_output
    assert "<code>" in full_output


@pytest.mark.asyncio
async def test_cmd_start_token_payload_routes_to_token(mock_bot, isolated_test_db):
    """
    When user arrives via https://t.me/<bot>?start=token, cmd_start routes to cmd_token.
    """
    user_id = 444111444
    priv_chat = MagicMock(spec=Chat)
    priv_chat.id = user_id
    priv_chat.type = "private"

    msg = MagicMock(spec=Message)
    msg.chat = priv_chat
    msg.from_user = MagicMock(spec=User, id=user_id, username="anon_user")
    msg.bot = mock_bot
    msg.text = "/start token"
    msg.caption = None
    msg.answer = AsyncMock()
    msg.delete = AsyncMock()

    state = AsyncMock()
    with patch("main.cmd_token", new_callable=AsyncMock) as mocked_cmd_token:
        await cmd_start(msg, state=state, board_id="b", stream="ru")
        assert mocked_cmd_token.called
        assert mocked_cmd_token.call_args[0][0] == msg


# =============================================================================
# 3. ANTI-SESSION-HIJACKING & MENU OWNERSHIP IN GROUPS
# =============================================================================

@pytest.mark.asyncio
async def test_check_menu_owner_core_logic():
    """
    Tests check_menu_owner, record_menu_owner, and get_menu_owner helper primitives.
    """
    chat_id = -100555
    msg_id = 1010
    owner_id = 11111
    stranger_id = 22222

    record_menu_owner(chat_id, msg_id, owner_id)

    # 1. Group chat with stranger -> False
    group_chat = MagicMock(spec=Chat, id=chat_id, type="supergroup")
    msg = MagicMock(spec=Message, chat=group_chat, message_id=msg_id, reply_to_message=None)
    cb_stranger = MagicMock(spec=types.CallbackQuery, message=msg, from_user=MagicMock(spec=User, id=stranger_id))

    assert check_menu_owner(cb_stranger) is False

    # 2. Group chat with legitimate owner -> True
    cb_owner = MagicMock(spec=types.CallbackQuery, message=msg, from_user=MagicMock(spec=User, id=owner_id))
    assert check_menu_owner(cb_owner) is True

    # 3. Private chat with stranger ID -> True (private chat menus are personal)
    priv_chat = MagicMock(spec=Chat, id=stranger_id, type="private")
    msg_priv = MagicMock(spec=Message, chat=priv_chat, message_id=msg_id, reply_to_message=None)
    cb_priv = MagicMock(spec=types.CallbackQuery, message=msg_priv, from_user=MagicMock(spec=User, id=stranger_id))
    assert check_menu_owner(cb_priv) is True

    # 4. Fallback to reply_to_message in group
    unrecorded_msg_id = 9999
    reply_msg = MagicMock(spec=Message, from_user=MagicMock(spec=User, id=owner_id))
    msg_with_reply = MagicMock(spec=Message, chat=group_chat, message_id=unrecorded_msg_id, reply_to_message=reply_msg)
    cb_stranger_reply = MagicMock(spec=types.CallbackQuery, message=msg_with_reply, from_user=MagicMock(spec=User, id=stranger_id))
    cb_owner_reply = MagicMock(spec=types.CallbackQuery, message=msg_with_reply, from_user=MagicMock(spec=User, id=owner_id))

    assert check_menu_owner(cb_stranger_reply) is False
    assert check_menu_owner(cb_owner_reply) is True


@pytest.mark.asyncio
async def test_bank_engine_rejects_session_hijacking_in_group(mock_bot, isolated_test_db):
    """
    Verifies that bank callbacks reject unauthorized users in public groups.
    """
    import bank_engine

    chat_id = -100888999
    msg_id = 5555
    owner_id = 3001
    stranger_id = 3002

    record_menu_owner(chat_id, msg_id, owner_id)

    group_chat = MagicMock(spec=Chat, id=chat_id, type="supergroup")
    msg = MagicMock(spec=Message, chat=group_chat, message_id=msg_id, reply_to_message=None)
    cb = MagicMock(spec=types.CallbackQuery, message=msg, from_user=MagicMock(spec=User, id=stranger_id))
    cb.answer = AsyncMock()

    # Test cb_bank_hub
    await bank_engine.cb_bank_hub(cb, board_id="b")
    assert cb.answer.called
    assert "Это чужое меню" in cb.answer.call_args[0][0]
    assert cb.answer.call_args[1].get("show_alert") is True

    # Test cb_bank_refresh
    cb.answer.reset_mock()
    await bank_engine.cb_bank_refresh(cb, board_id="b")
    assert cb.answer.called
    assert "Это чужое меню" in cb.answer.call_args[0][0]

    # Test cb_bank_deposit_menu
    cb.answer.reset_mock()
    await bank_engine.cb_bank_deposit_menu(cb, board_id="b")
    assert cb.answer.called
    assert "Это чужое меню" in cb.answer.call_args[0][0]

    # Test cb_bank_withdraw_menu
    cb.answer.reset_mock()
    await bank_engine.cb_bank_withdraw_menu(cb, board_id="b")
    assert cb.answer.called
    assert "Это чужое меню" in cb.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_wardrobe_callbacks_reject_session_hijacking_in_group(mock_bot, isolated_test_db):
    """
    Verifies that wardrobe callbacks in main.py reject unauthorized users in public groups.
    """
    chat_id = -100777888
    msg_id = 4444
    owner_id = 4001
    stranger_id = 4002

    record_menu_owner(chat_id, msg_id, owner_id)

    group_chat = MagicMock(spec=Chat, id=chat_id, type="supergroup")
    msg = MagicMock(spec=Message, chat=group_chat, message_id=msg_id, reply_to_message=None)
    cb = MagicMock(spec=types.CallbackQuery, message=msg, from_user=MagicMock(spec=User, id=stranger_id))
    cb.answer = AsyncMock()

    # 1. cb_wardrobe_dressing_room
    await main.cb_wardrobe_dressing_room(cb, board_id="b")
    assert cb.answer.called
    assert "Это чужое меню" in cb.answer.call_args[0][0]
    assert cb.answer.call_args[1].get("show_alert") is True

    # 2. cb_wardrobe_page
    cb.answer.reset_mock()
    cb.data = "wardrobe_page_2"
    await main.cb_wardrobe_page(cb, board_id="b")
    assert cb.answer.called
    assert "Это чужое меню" in cb.answer.call_args[0][0]

    # 3. cb_wardrobe_equip
    cb.answer.reset_mock()
    cb.data = "wardrobe_equip_hat_tinfoil"
    await main.cb_wardrobe_equip(cb, board_id="b")
    assert cb.answer.called
    assert "Это чужое меню" in cb.answer.call_args[0][0]

    # 4. cb_wardrobe_unequip
    cb.answer.reset_mock()
    cb.data = "wardrobe_unequip_head"
    await main.cb_wardrobe_unequip(cb, board_id="b")
    assert cb.answer.called
    assert "Это чужое меню" in cb.answer.call_args[0][0]

    # 5. callback_repair_all
    cb.answer.reset_mock()
    cb.data = "repair_all_items"
    await main.callback_repair_all(cb, board_id="b")
    assert cb.answer.called
    assert "Это чужое меню" in cb.answer.call_args[0][0]


# =============================================================================
# 4. NAVIGATION UX & NO DUPLICATE BUTTONS ON SAME ROW
# =============================================================================

def test_auction_keyboard_no_duplicate_back_and_main_menu():
    """
    Verifies build_auction_list_kb does not have [◀️ Назад] and [⚡ Главное меню] on the same row.
    """
    kb = auction_engine.build_auction_list_kb(page=1, total_pages=3)
    for row in kb.inline_keyboard:
        row_texts = [btn.text for btn in row]
        # Must not contain both back and main menu on the same row
        has_back = any("Назад" in t for t in row_texts)
        has_main = any("Главное меню" in t for t in row_texts)
        assert not (has_back and has_main), f"Found duplicate buttons on row: {row_texts}"


def test_casino_keyboards_no_duplicate_back_and_main_menu():
    """
    Verifies casino hub, blackjack and replay keyboards do not have [◀️ Назад] and [⚡ Главное меню] on the same row.
    """
    keyboards = [
        casino_engine.get_casino_hub_keyboard(),
        casino_engine.get_blackjack_keyboard(bet=100),
        casino_engine.get_blackjack_replay_keyboard(bet=100, balance=1000),
    ]

    for kb in keyboards:
        for row in kb.inline_keyboard:
            row_texts = [btn.text for btn in row]
            has_back = any("◀️ Назад" == t for t in row_texts)
            has_main = any("Главное меню" in t for t in row_texts)
            assert not (has_back and has_main), f"Found duplicate buttons on row: {row_texts}"


def test_market_keyboard_no_duplicate_back_and_main_menu():
    """
    Verifies build_market_main_menu_kb has no duplicate [◀️ Назад] and [⚡ Главное меню] on the same row.
    """
    kb = build_market_main_menu_kb()
    for row in kb.inline_keyboard:
        row_texts = [btn.text for btn in row]
        has_back = any("◀️ Назад" == t for t in row_texts)
        has_main = any("Главное меню" in t for t in row_texts)
        assert not (has_back and has_main), f"Found duplicate buttons on row: {row_texts}"


@pytest.mark.asyncio
async def test_market_catalog_and_lot_view_preserves_category_sort_page(mock_bot, isolated_test_db):
    """
    Verifies that build_market_catalog_kb encodes category, sort_order, page in market_lot callback,
    and cb_market_lot creates a return button [◀️ Назад в каталог] that preserves them.
    """
    category = "weapons"
    sort_order = "price_desc"
    page = 3
    total_pages = 5
    sample_items = [
        {"id": 42, "item_name": "⚔️ Меч Абу", "price": 1500.0, "item_type": "weapons"}
    ]

    # 1. Generate catalog keyboard
    kb = build_market_catalog_kb(category, sort_order, page, total_pages, sample_items)
    lot_btn = kb.inline_keyboard[0][0]
    expected_cb_data = f"market_lot:42:{category}:{sort_order}:{page}"
    assert lot_btn.callback_data == expected_cb_data

    # 2. Insert mock listing into DB to test cb_market_lot
    db = await get_pool()
    await market_engine.ensure_market_schema(db)
    async with db.execute(
        """
        INSERT INTO MarketListings (id, seller_id, item_id, item_name, item_type, price, status, item_data, created_at)
        VALUES (42, 100, 'item_sword', '⚔️ Меч Абу', 'weapons', 1500.0, 'active', '{}', 1700000000)
        """
    ):
        await db.commit()

    cb = MagicMock(spec=types.CallbackQuery)
    cb.data = expected_cb_data
    cb.from_user = MagicMock(spec=User, id=100)
    cb.message = MagicMock(spec=Message, chat=MagicMock(spec=Chat, type="private"))
    cb.answer = AsyncMock()

    with patch("market_engine._render_market_view", new_callable=AsyncMock) as mocked_render:
        await cb_market_lot(cb, board_id="b")
        assert mocked_render.called
        render_args = mocked_render.call_args[0]
        rendered_kb = render_args[2]

        back_btn = None
        for row in rendered_kb.inline_keyboard:
            for b in row:
                if "Назад в каталог" in b.text:
                    back_btn = b
                    break

        assert back_btn is not None
        assert back_btn.callback_data == f"market_cat:{category}:{sort_order}:{page}"
