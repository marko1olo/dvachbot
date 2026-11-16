# -*- coding: utf-8 -*-
"""
tests/test_econ_hubs_and_navigation_fixes.py — Comprehensive Test Suite for
Econ Hubs Navigation Standardization, Spinner Prevention & MessageIsNotModified Suppression.

Tests:
1. Keyboard Structure: Standardized navigation ([⚡ Главное меню] and [◀️ Назад])
   across all bank, market, auction, casino, and loan menus.
2. Spinner Prevention: Every callback handler ALWAYS calls callback.answer() / safe_callback_answer()
   under success, error, invalid parameters, and repeated clicks.
3. Message is not modified Suppression: Graceful handling without throwing exceptions or
   spamming duplicate banner messages.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

# Modules under test
import bank_engine
import market_engine
import auction_engine
import casino_engine
import heist_and_loan_engine
import main


# =============================================================================
# HELPER FUNCTIONS FOR KEYBOARD INSPECTION
# =============================================================================

def find_button_by_callback(kb: InlineKeyboardMarkup, cb_data: str):
    """Finds first button with matching callback_data in inline keyboard."""
    for row in kb.inline_keyboard:
        for btn in row:
            if btn.callback_data == cb_data:
                return btn
    return None


def find_button_by_text(kb: InlineKeyboardMarkup, needle: str):
    """Finds first button whose text contains the specified needle."""
    for row in kb.inline_keyboard:
        for btn in row:
            if needle.lower() in (btn.text or "").lower():
                return btn
    return None


def assert_has_navigation_buttons(kb: InlineKeyboardMarkup, back_needle: str = "назад", main_menu_data: str = "menu_main"):
    """
    Asserts that the keyboard contains both a Back button (containing back_needle or ◀️)
    and a Main Menu button (⚡ Главное меню).
    """
    assert isinstance(kb, InlineKeyboardMarkup), f"Expected InlineKeyboardMarkup, got {type(kb)}"

    # 1. Check Main Menu button
    main_menu_btn = find_button_by_callback(kb, main_menu_data)
    if not main_menu_btn:
        main_menu_btn = find_button_by_text(kb, "главное меню")
    assert main_menu_btn is not None, f"Keyboard missing [⚡ Главное меню] button! Buttons: {[[b.text for b in r] for r in kb.inline_keyboard]}"

    # 2. Check Back button
    back_btn = find_button_by_text(kb, back_needle)
    if not back_btn:
        back_btn = find_button_by_text(kb, "◀️")
    if not back_btn:
        back_btn = find_button_by_text(kb, "⬅️")
    assert back_btn is not None, f"Keyboard missing Back button (needle: '{back_needle}')! Buttons: {[[b.text for b in r] for r in kb.inline_keyboard]}"


# =============================================================================
# PART 1: KEYBOARD STRUCTURE & NAVIGATION STANDARDIZATION TESTS
# =============================================================================

class TestEconKeyboardsNavigation:
    """Verifies that every screen and sub-screen in the economy hubs has return & back navigation."""

    def test_bank_hub_keyboard(self):
        kb = bank_engine.build_bank_hub_kb(dirty_balance=0.0)
        assert_has_navigation_buttons(kb)
        # Check dirty balance branch as well
        kb_dirty = bank_engine.build_bank_hub_kb(dirty_balance=1000.0)
        assert_has_navigation_buttons(kb_dirty)

    def test_bank_deposit_tiers_keyboard(self):
        kb = bank_engine.build_deposit_tiers_kb()
        assert_has_navigation_buttons(kb, back_needle="назад")

    def test_bank_deposit_presets_keyboard(self):
        _, kb = bank_engine.build_deposit_presets_kb(tier_id="sych", wallet_balance=50000.0)
        assert_has_navigation_buttons(kb, back_needle="назад")

    def test_bank_withdraw_deposits_empty_keyboard(self):
        _, kb = bank_engine.build_withdraw_deposits_view(deposits=[], page=0)
        assert_has_navigation_buttons(kb, back_needle="назад")

    def test_bank_withdraw_deposits_populated_keyboard(self):
        mock_deposit = {
            "id": 1,
            "short_name": "Сейф",
            "tier_name": "Сейф Сыча",
            "tier_id": "sych",
            "principal": 1000.0,
            "total_value": 1050.0,
            "is_locked": False,
            "accrued_interest": 50.0,
            "remaining_lock_sec": 0,
        }
        _, kb = bank_engine.build_withdraw_deposits_view(deposits=[mock_deposit], page=0)
        assert_has_navigation_buttons(kb, back_needle="назад")

    def test_market_main_menu_keyboard(self):
        kb = market_engine.build_market_main_menu_kb()
        assert_has_navigation_buttons(kb, back_needle="назад")

    def test_market_my_lots_keyboard(self):
        mock_lot = {
            "id": 42,
            "item_name": "Золотой Калаш",
            "price": 5000.0,
        }
        kb = market_engine.build_my_lots_kb([mock_lot], page=1, total_pages=1)
        assert_has_navigation_buttons(kb, back_needle="назад")

    def test_market_catalog_keyboard(self):
        mock_item = {
            "id": 7,
            "item_name": "Бронежилет Абу",
            "price": 1500.0,
        }
        kb = market_engine.build_market_catalog_kb("all", "price_asc", 1, 1, [mock_item])
        assert_has_navigation_buttons(kb, back_needle="назад")

    def test_auction_list_keyboard_single_and_multi_page(self):
        kb_single = auction_engine.build_auction_list_kb(1, 1)
        assert_has_navigation_buttons(kb_single, back_needle="назад")

        kb_multi = auction_engine.build_auction_list_kb(2, 5)
        assert_has_navigation_buttons(kb_multi, back_needle="назад")

    def test_casino_hub_keyboard(self):
        kb = casino_engine.get_casino_hub_keyboard()
        assert_has_navigation_buttons(kb, back_needle="назад")

    def test_slots_lobby_keyboard(self):
        kb = casino_engine.get_slots_lobby_keyboard(bet=100, balance=10000)
        assert_has_navigation_buttons(kb, back_needle="назад")

    def test_slots_in_game_keyboard(self):
        kb = casino_engine.get_slots_keyboard(bet=100, balance=10000)
        assert_has_navigation_buttons(kb, back_needle="назад")

    def test_coinflip_lobby_keyboard(self):
        kb = casino_engine.get_coinflip_lobby_keyboard(bet=100, balance=10000)
        assert_has_navigation_buttons(kb, back_needle="назад")

    def test_coinflip_in_game_keyboard(self):
        kb = casino_engine.get_coinflip_keyboard(bet=100, balance=10000)
        assert_has_navigation_buttons(kb, back_needle="назад")

    def test_blackjack_lobby_keyboard(self):
        kb = casino_engine.get_blackjack_lobby_keyboard(bet=100, balance=10000)
        assert_has_navigation_buttons(kb, back_needle="назад")

    def test_blackjack_in_game_and_replay_keyboards(self):
        kb_game = casino_engine.get_blackjack_keyboard(bet=100, can_double=True)
        assert_has_navigation_buttons(kb_game, back_needle="назад")

        kb_replay = casino_engine.get_blackjack_replay_keyboard(bet=100, balance=10000)
        assert_has_navigation_buttons(kb_replay, back_needle="назад")

    def test_roulette_lobby_and_in_game_keyboards(self):
        kb_lobby = casino_engine.get_roulette_lobby_keyboard(bet=100, balance=10000)
        assert_has_navigation_buttons(kb_lobby, back_needle="назад")

        kb_game = casino_engine.get_roulette_keyboard(bet=100, current_mult=1.5)
        assert_has_navigation_buttons(kb_game, back_needle="назад")

    def test_loan_and_heist_keyboards(self):
        kb_loan = heist_and_loan_engine.build_loan_keyboard()
        assert_has_navigation_buttons(kb_loan, back_needle="назад")

        kb_launder = heist_and_loan_engine.build_launder_keyboard()
        assert_has_navigation_buttons(kb_launder, back_needle="назад")


# =============================================================================
# PART 2: SPINNER PREVENTION & GUARANTEED callback.answer() INVOCATION TESTS
# =============================================================================

@pytest.fixture
def mock_callback():
    """Generates an aiogram types.CallbackQuery mock with answer tracking."""
    cb = MagicMock(spec=types.CallbackQuery)
    cb.data = "noop"
    cb.answer = AsyncMock(return_value=True)
    cb.from_user = MagicMock(id=99999, full_name="Anon Pilot", first_name="Anon")
    cb.bot = MagicMock()

    msg = MagicMock(spec=types.Message)
    msg.chat = MagicMock(id=-100123)
    msg.message_id = 4242
    msg.photo = [MagicMock()]
    msg.caption = "Existing Caption"
    msg.text = None
    msg.edit_caption = AsyncMock()
    msg.edit_text = AsyncMock()
    msg.delete = AsyncMock()
    msg.answer = AsyncMock()
    cb.message = msg
    return cb


@pytest.mark.asyncio
class TestCallbackSpinnersElimination:
    """Verifies that all handlers reliably call callback.answer() in success, failure and edge cases."""

    async def test_bank_hub_callback_always_answers_on_success(self, mock_callback):
        mock_callback.data = "bank_main_hub"
        with patch("bank_engine.get_pool", AsyncMock()), \
             patch("bank_engine.get_user_global_balance", AsyncMock(return_value=1000.0)), \
             patch("bank_engine.get_user_bank_summary", AsyncMock(return_value=(500.0, 10.0, []))), \
             patch("bank_engine._render_bank_view", AsyncMock()):
            await bank_engine.cb_bank_hub(mock_callback)
        mock_callback.answer.assert_called()

    async def test_bank_hub_callback_always_answers_on_exception(self, mock_callback):
        mock_callback.data = "bank_main_hub"
        with patch("bank_engine.get_pool", AsyncMock(side_effect=RuntimeError("DB explosion!"))):
            with pytest.raises(RuntimeError):
                await bank_engine.cb_bank_hub(mock_callback)
        # Even with uncaught exception, finally block must answer callback!
        mock_callback.answer.assert_called()

    async def test_bank_refresh_callback_answers_on_success(self, mock_callback):
        mock_callback.data = "bank_refresh"
        with patch("bank_engine.get_pool", AsyncMock()), \
             patch("bank_engine.get_user_global_balance", AsyncMock(return_value=1000.0)), \
             patch("bank_engine.get_user_bank_summary", AsyncMock(return_value=(500.0, 10.0, []))), \
             patch("bank_engine._render_bank_view", AsyncMock()):
            await bank_engine.cb_bank_refresh(mock_callback)
        mock_callback.answer.assert_called()

    async def test_bank_refresh_callback_answers_on_exception(self, mock_callback):
        mock_callback.data = "bank_refresh"
        with patch("bank_engine.get_pool", AsyncMock(side_effect=RuntimeError("Timeout"))):
            with pytest.raises(RuntimeError):
                await bank_engine.cb_bank_refresh(mock_callback)
        mock_callback.answer.assert_called()

    async def test_market_noop_callback_answers(self, mock_callback):
        mock_callback.data = "market_noop"
        await market_engine.cb_market_noop(mock_callback)
        mock_callback.answer.assert_called()

    async def test_market_main_hub_callback_answers_on_success_and_error(self, mock_callback):
        mock_callback.data = "market_main_hub"
        with patch("market_engine.get_pool", AsyncMock()), \
             patch("market_engine.get_user_global_balance", AsyncMock(return_value=1500.0)), \
             patch("market_engine._render_market_view", AsyncMock()):
            await market_engine.cb_market_main_hub(mock_callback)
        mock_callback.answer.assert_called()

        mock_callback.answer.reset_mock()
        with patch("market_engine.get_pool", AsyncMock()), \
             patch("market_engine.get_user_global_balance", AsyncMock(return_value=1500.0)), \
             patch("market_engine._render_market_view", AsyncMock(side_effect=ValueError("Render fault"))):
            with pytest.raises(ValueError):
                await market_engine.cb_market_main_hub(mock_callback)
        mock_callback.answer.assert_called()

    async def test_market_lot_not_found_answers_and_stops_spinner(self, mock_callback):
        mock_callback.data = "market_lot:999999"
        with patch("market_engine.get_pool", AsyncMock()), \
             patch("market_engine.get_market_listing", AsyncMock(return_value=None)):
            await market_engine.cb_market_lot(mock_callback)
        mock_callback.answer.assert_called()

    async def test_auction_page_callback_answers_on_success_and_error(self, mock_callback):
        mock_callback.data = "auc_page:1"
        with patch("auction_engine.get_pool", AsyncMock()), \
             patch("auction_engine.get_active_auctions", AsyncMock(return_value=[])), \
             patch("auction_engine.build_auction_list_kb", MagicMock()):
            await auction_engine.cb_auction_page(mock_callback)
        mock_callback.answer.assert_called()

        mock_callback.answer.reset_mock()
        with patch("auction_engine.get_pool", AsyncMock(side_effect=RuntimeError("Auction lock down"))):
            with pytest.raises(RuntimeError):
                await auction_engine.cb_auction_page(mock_callback)
        mock_callback.answer.assert_called()

    async def test_auction_noop_callback_answers(self, mock_callback):
        mock_callback.data = "auc_noop"
        await auction_engine.cb_auc_noop(mock_callback)
        mock_callback.answer.assert_called()

    async def test_casino_main_hub_callback_answers_on_success(self, mock_callback):
        mock_callback.data = "casino_main_hub"
        with patch("main.get_pool", AsyncMock()), \
             patch("main.get_user_global_balance", AsyncMock(return_value=5000.0)), \
             patch("common.bot_helpers.render_menu_transition", AsyncMock()):
            await main.cb_casino_main_hub(mock_callback)
        mock_callback.answer.assert_called()

    async def test_casino_main_hub_callback_answers_on_exception(self, mock_callback):
        mock_callback.data = "casino_main_hub"
        with patch("main.get_pool", AsyncMock(side_effect=RuntimeError("Casino DB failed"))):
            with pytest.raises(RuntimeError):
                await main.cb_casino_main_hub(mock_callback)
        mock_callback.answer.assert_called()

    async def test_casino_handler_hub_answers_callback(self, mock_callback):
        mock_callback.data = "cas:hub"
        with patch("main.get_pool", AsyncMock()), \
             patch("main.get_user_global_balance", AsyncMock(return_value=5000.0)), \
             patch("common.bot_helpers.render_menu_transition", AsyncMock()):
            await main.cb_casino_handler(mock_callback)
        mock_callback.answer.assert_called()

    async def test_casino_handler_unknown_subaction_answers_callback(self, mock_callback):
        mock_callback.data = "cas:unknown_action_xyz:123"
        with patch("main.get_pool", AsyncMock()):
            await main.cb_casino_handler(mock_callback)
        mock_callback.answer.assert_called()

    async def test_casino_handler_exception_guarantees_answer(self, mock_callback):
        mock_callback.data = "cas:slots:spin:100"
        with patch("main.get_pool", AsyncMock(side_effect=RuntimeError("Spin lock error"))):
            with pytest.raises(RuntimeError):
                await main.cb_casino_handler(mock_callback)
        mock_callback.answer.assert_called()

    async def test_loan_hub_callback_answers_when_user_id_zero(self, mock_callback):
        mock_callback.from_user = None
        mock_callback.data = "loan_hub"
        await heist_and_loan_engine.cb_loan_hub(mock_callback)
        mock_callback.answer.assert_called()

    async def test_launder_hub_callback_answers_on_exception(self, mock_callback):
        mock_callback.data = "launder_hub"
        with patch("heist_and_loan_engine.get_user_active_items", AsyncMock(side_effect=RuntimeError("Launder failed"))):
            with pytest.raises(RuntimeError):
                await heist_and_loan_engine.cb_launder_hub(mock_callback)
        mock_callback.answer.assert_called()


# =============================================================================
# PART 3: SUPPRESSION OF TelegramBadRequest: Message is not modified
# =============================================================================

@pytest.mark.asyncio
class TestMessageIsNotModifiedSuppression:
    """Verifies that repeat clicks do not throw uncaught errors or spam new messages."""

    async def test_bank_refresh_unmodified_shows_toast_without_error(self, mock_callback):
        """
        When user taps '🔄 Обновить проценты' and the message hasn't changed,
        Telegram throws TelegramBadRequest: message is not modified.
        The renderer must catch this, call callback.answer with toast, and not crash.
        """
        mock_callback.data = "bank_refresh"
        mock_callback.message.edit_caption = AsyncMock(side_effect=TelegramBadRequest(
            method="editMessageCaption",
            message="Bad Request: message is not modified: specified new message content and reply markup are exactly the same"
        ))

        with patch("bank_engine.get_pool", AsyncMock()), \
             patch("bank_engine.get_user_global_balance", AsyncMock(return_value=1000.0)), \
             patch("bank_engine.get_user_bank_summary", AsyncMock(return_value=(500.0, 10.0, []))):
            await bank_engine.cb_bank_refresh(mock_callback)

        # callback.answer was called with toast notification
        mock_callback.answer.assert_called()

    async def test_casino_hub_repeat_click_suppresses_duplicate_banner_spam(self, mock_callback):
        """
        When user clicks '🔙 Меню Казино' while ALREADY on the casino hub,
        edit_caption throws 'message is not modified'.
        The system must catch it cleanly and MUST NOT call send_banner_message to spam a new card!
        """
        mock_callback.data = "cas:hub"
        mock_callback.message.edit_caption = AsyncMock(side_effect=TelegramBadRequest(
            method="editMessageCaption",
            message="Bad Request: message is not modified: specified new message content and reply markup are exactly the same"
        ))

        mock_send_banner = AsyncMock()
        with patch("main.get_pool", AsyncMock()), \
             patch("main.get_user_global_balance", AsyncMock(return_value=5000.0)), \
             patch("banner_manager.send_banner_message", mock_send_banner):
            await main.cb_casino_handler(mock_callback)

        # send_banner_message must NOT be called on Message is not modified!
        mock_send_banner.assert_not_called()
        mock_callback.answer.assert_any_call("🔄 Информация актуальна")

    async def test_slots_lobby_repeat_bet_preset_does_not_spam_banner(self, mock_callback):
        """
        When user clicks the bet preset that is already active (e.g. 100 ₪),
        edit_caption throws 'message is not modified'.
        _show_slots_lobby must suppress it and not call send_banner_message.
        """
        mock_msg = mock_callback.message
        mock_msg.edit_caption = AsyncMock(side_effect=TelegramBadRequest(
            method="editMessageCaption",
            message="Bad Request: message is not modified"
        ))
        mock_send_banner = AsyncMock()

        with patch("main.get_pool", AsyncMock()), \
             patch("main.get_user_global_balance", AsyncMock(return_value=5000.0)), \
             patch("banner_manager.send_banner_message", mock_send_banner):
            await main._show_slots_lobby(
                bot=mock_callback.bot,
                chat_id=12345,
                user_id=mock_callback.from_user.id,
                board_id="b",
                bet=100,
                message_to_edit=mock_msg
            )

        mock_send_banner.assert_not_called()

    async def test_coinflip_lobby_repeat_bet_preset_does_not_spam_banner(self, mock_callback):
        """
        Same for coinflip lobby.
        """
        mock_msg = mock_callback.message
        mock_msg.edit_caption = AsyncMock(side_effect=TelegramBadRequest(
            method="editMessageCaption",
            message="Bad Request: message is not modified"
        ))
        mock_send_banner = AsyncMock()

        with patch("main.get_pool", AsyncMock()), \
             patch("main.get_user_global_balance", AsyncMock(return_value=5000.0)), \
             patch("banner_manager.send_banner_message", mock_send_banner):
            await main._show_coinflip_lobby(
                bot=mock_callback.bot,
                chat_id=12345,
                user_id=mock_callback.from_user.id,
                board_id="b",
                bet=100,
                message_to_edit=mock_msg
            )

        mock_send_banner.assert_not_called()

    async def test_blackjack_lobby_repeat_bet_preset_does_not_spam_banner(self, mock_callback):
        """
        Same for blackjack lobby.
        """
        mock_msg = mock_callback.message
        mock_msg.edit_caption = AsyncMock(side_effect=TelegramBadRequest(
            method="editMessageCaption",
            message="Bad Request: message is not modified"
        ))
        mock_send_banner = AsyncMock()

        with patch("main.get_pool", AsyncMock()), \
             patch("main.get_user_global_balance", AsyncMock(return_value=5000.0)), \
             patch("banner_manager.send_banner_message", mock_send_banner):
            await main._show_blackjack_lobby(
                bot=mock_callback.bot,
                chat_id=12345,
                user_id=mock_callback.from_user.id,
                board_id="b",
                bet=100,
                message_to_edit=mock_msg
            )

        mock_send_banner.assert_not_called()

    async def test_roulette_lobby_repeat_bet_preset_does_not_spam_banner(self, mock_callback):
        """
        Same for roulette lobby.
        """
        mock_msg = mock_callback.message
        mock_msg.edit_caption = AsyncMock(side_effect=TelegramBadRequest(
            method="editMessageCaption",
            message="Bad Request: message is not modified"
        ))
        mock_send_banner = AsyncMock()

        with patch("main.get_pool", AsyncMock()), \
             patch("main.get_user_global_balance", AsyncMock(return_value=5000.0)), \
             patch("banner_manager.send_banner_message", mock_send_banner):
            await main._show_roulette_lobby(
                bot=mock_callback.bot,
                chat_id=12345,
                user_id=mock_callback.from_user.id,
                board_id="b",
                bet=100,
                message_to_edit=mock_msg
            )

        mock_send_banner.assert_not_called()
