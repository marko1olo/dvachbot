import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import json
import time

@pytest.mark.asyncio
async def test_slots_spin_animation_in_place():
    """Verify that _execute_slots_spin edits caption in-place with spinning animation and then final reels."""
    from main import _execute_slots_spin
    
    mock_bot = AsyncMock()
    mock_msg = AsyncMock()
    mock_msg.chat.id = 12345
    mock_msg.edit_caption = AsyncMock()

    mock_db = AsyncMock()
    
    with patch("main.casino_engine.check_casino_cooldown", return_value=(True, 0)), \
         patch("main.get_pool", return_value=mock_db), \
         patch("main.get_user_global_balance", return_value=10000), \
         patch("main.casino_engine.roll_slots", return_value=(["🍒", "🍒", "🍒"], 9.0, "Три Вишенки")), \
         patch("main.calculate_win_tax", return_value=(0, 900)), \
         patch("main.add_user_global_balance", return_value=10900), \
         patch("main.record_user_transaction", return_value=None), \
         patch("main.add_to_abu_fund", return_value=None), \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:

        await _execute_slots_spin(
            bot=mock_bot,
            chat_id=12345,
            user_id=999,
            board_id="b",
            bet=100,
            message_to_edit=mock_msg
        )

        # Verify that asyncio.sleep was called with 0.9s for the spin animation
        mock_sleep.assert_called_once_with(0.9)

        # Verify edit_caption was called twice: 1st for spin animation, 2nd for result
        assert mock_msg.edit_caption.call_count == 2
        first_call = mock_msg.edit_caption.call_args_list[0]
        second_call = mock_msg.edit_caption.call_args_list[1]

        assert "🌀" in first_call[1]["caption"]
        assert "Барабаны крутятся" in first_call[1]["caption"]

        assert "🍒" in second_call[1]["caption"]
        assert "Три Вишенки" in second_call[1]["caption"]
        assert "+900 ₪" in second_call[1]["caption"]
        assert second_call[1]["reply_markup"] is not None


@pytest.mark.asyncio
async def test_coinflip_animation_in_place():
    """Verify that _execute_coinflip edits caption in-place with spinning coin animation and then final result."""
    from main import _execute_coinflip

    mock_bot = AsyncMock()
    mock_msg = AsyncMock()
    mock_msg.chat.id = 12345
    mock_msg.edit_caption = AsyncMock()

    mock_db = AsyncMock()

    with patch("main.casino_engine.check_casino_cooldown", return_value=(True, 0)), \
         patch("main.get_pool", return_value=mock_db), \
         patch("main.get_user_global_balance", return_value=5000), \
         patch("main.casino_engine.play_coinflip", return_value=("🦅 ОРЕЛ", True, 1.95, "Победа")), \
         patch("main.calculate_win_tax", return_value=(0, 95)), \
         patch("main.add_user_global_balance", return_value=5095), \
         patch("main.record_user_transaction", return_value=None), \
         patch("main._get_user_active_items", return_value={}), \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:

        await _execute_coinflip(
            bot=mock_bot,
            chat_id=12345,
            user_id=888,
            board_id="b",
            bet=100,
            chosen_side="heads",
            message_to_edit=mock_msg
        )

        mock_sleep.assert_called_once_with(0.7)
        assert mock_msg.edit_caption.call_count == 2
        first_call = mock_msg.edit_caption.call_args_list[0]
        second_call = mock_msg.edit_caption.call_args_list[1]

        assert "ПОДБРАСЫВАЕМ ШЕКЕЛЬ" in first_call[1]["caption"]
        assert "🦅 ОРЕЛ" in second_call[1]["caption"]
        assert "+195 ₪" in second_call[1]["caption"]


@pytest.mark.asyncio
async def test_jackpot_news_filters():
    """Verify publish_casino_jackpot_news filters slots vs pvp/roulette correctly."""
    from news_channel_publisher import publish_casino_jackpot_news

    mock_bot = AsyncMock()
    mock_bot.get_me.return_value = MagicMock(username="tgach_bot")

    with patch("news_channel_publisher.get_target_channels", return_value=(-100123, -100123)), \
         patch("news_channel_publisher.send_channel_content", new_callable=AsyncMock, return_value=777) as mock_send:

        # 1. Slots < 4.0x must be rejected
        res_slots_low = await publish_casino_jackpot_news(
            bot=mock_bot, user_id=1, game_type="slots", bet_amount=100000, win_amount=180000, multiplier=1.8
        )
        assert res_slots_low is False

        # 2. Slots >= 4.0x accepted
        res_slots_high = await publish_casino_jackpot_news(
            bot=mock_bot, user_id=1, game_type="slots", bet_amount=1000, win_amount=9000, multiplier=9.0, symbols="[🍒 | 🍒 | 🍒]"
        )
        assert res_slots_high is True

        # 3. Dice duel >= 50k accepted
        res_dice = await publish_casino_jackpot_news(
            bot=mock_bot, user_id=2, game_type="dice", bet_amount=30000, win_amount=57000, multiplier=1.9, symbols="⚅ ⚅ vs ⚁ ⚂"
        )
        assert res_dice is True

        # 4. Russian roulette x4.0+ accepted
        res_rr = await publish_casino_jackpot_news(
            bot=mock_bot, user_id=3, game_type="roulette", bet_amount=5000, win_amount=27500, multiplier=5.5, symbols="Выжил 4 выстрела!"
        )
        assert res_rr is True


@pytest.mark.asyncio
async def test_open_duel_card_keyboard_has_accept_button():
    """Verify that open duel creation generates a card with both Accept and Cancel buttons."""
    from main import _handle_duel_create

    mock_msg = AsyncMock()
    mock_msg.from_user = MagicMock(id=5555)
    mock_msg.chat = MagicMock(id=-100999, type="supergroup")
    mock_msg.reply_to_message = None
    mock_msg.answer = AsyncMock()
    mock_msg.delete = AsyncMock()

    sent_card = AsyncMock()
    sent_card.chat.id = -100999
    sent_card.message_id = 42
    mock_msg.answer.return_value = sent_card

    mock_db = AsyncMock()

    with patch("main.get_pool", return_value=mock_db), \
         patch("main.get_user_global_balance", return_value=50000), \
         patch("main.deduct_user_global_balance", return_value=(True, 49000)), \
         patch("main.record_user_transaction", return_value=None), \
         patch("main.make_duel_token", return_value="tok123"):

        await _handle_duel_create(mock_msg, board_id="b", args=["1000"], stream="ru")

        mock_msg.answer.assert_called_once()
        call_kwargs = mock_msg.answer.call_args[1]
        kb = call_kwargs["reply_markup"]
        
        # Verify both Accept and Cancel buttons are present on the public card
        buttons = [btn for row in kb.inline_keyboard for btn in row]
        button_callbacks = [b.callback_data for b in buttons]
        assert "duel_accept:tok123" in button_callbacks
        assert "duel_cancel:tok123" in button_callbacks
