import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import ast
import random
import sys

# Test cmd_dossier handler directly
@pytest.mark.asyncio
async def test_cmd_dossier_insufficient_funds():
    import main
    msg = MagicMock()
    msg.from_user.id = 12345
    msg.chat.id = -100123
    msg.reply_to_message = None
    msg.answer = AsyncMock()

    with patch("main.get_pool", new_callable=AsyncMock) as mock_pool, \
         patch("main.get_user_global_balance", new_callable=AsyncMock, return_value=100) as mock_bal, \
         patch("main.spawn_task"):
        await main.cmd_dossier(msg, board_id="b")
        assert msg.answer.called
        args, kwargs = msg.answer.call_args
        assert "ОТКАЗ В ДОСТУПЕ" in args[0]
        assert "750" in args[0]

@pytest.mark.asyncio
async def test_cmd_dossier_all_error_modes():
    import main
    
    modes_to_test = [
        "wrong_real_anon",
        "legendary_fake",
        "mess_clues",
        "mess_psych",
        "mess_articles",
        "mess_spill",
        "data_skew",
        None
    ]

    for mode in modes_to_test:
        msg = MagicMock()
        msg.from_user.id = 12345
        msg.chat.id = -100123
        msg.reply_to_message = None
        msg.bot = MagicMock()

        mock_db = MagicMock()
        # Mock cursor for wrong_real_anon
        mock_cursor = AsyncMock()
        mock_cursor.fetchone = AsyncMock(return_value=(99999,))
        mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_cursor.__aexit__ = AsyncMock(return_value=None)
        mock_db.execute = MagicMock(return_value=mock_cursor)

        with patch("main.get_pool", new_callable=AsyncMock, return_value=mock_db), \
             patch("main.get_user_global_balance", new_callable=AsyncMock, return_value=5000), \
             patch("main.deduct_user_global_balance", new_callable=AsyncMock, return_value=(True, 4250)), \
             patch("main.record_user_transaction", new_callable=AsyncMock), \
             patch("main.add_to_abu_fund", new_callable=AsyncMock), \
             patch("main.spawn_task"), \
             patch("banner_manager.send_banner_message", new_callable=AsyncMock) as mock_send_banner:

            # Patch random to force specific error_mode
            if mode is None:
                patch_err = patch("random.random", return_value=0.99)
                patch_choices = patch("random.choices", return_value=["mess_clues"])
            else:
                patch_err = patch("random.random", return_value=0.10)
                patch_choices = patch("random.choices", return_value=[mode])

            with patch_err, patch_choices:
                await main.cmd_dossier(msg, board_id="b")

            assert mock_send_banner.called, f"Failed for mode {mode}"
            call_kwargs = mock_send_banner.call_args.kwargs
            caption = call_kwargs["caption"]
            assert "ЛИЧНОЕ ДЕЛО АНОНА" in caption, f"No header in mode {mode}"
            if mode is not None:
                assert "⚠️ КАРТОТЕЧНЫЙ СБОЙ" in caption, f"No warning banner in mode {mode}: {caption}"
            else:
                assert "⚠️ КАРТОТЕЧНЫЙ СБОЙ" not in caption, f"Unexpected warning in mode None"

@pytest.mark.asyncio
async def test_legendary_profiles_variety():
    import main
    # Ensure all 6 legendary characters can be selected without errors
    captured_badges = set()
    for _ in range(50):
        msg = MagicMock()
        msg.from_user.id = 12345
        msg.chat.id = -100123
        msg.reply_to_message = None
        msg.bot = MagicMock()

        mock_db = MagicMock()

        with patch("main.get_pool", new_callable=AsyncMock, return_value=mock_db), \
             patch("main.get_user_global_balance", new_callable=AsyncMock, return_value=5000), \
             patch("main.deduct_user_global_balance", new_callable=AsyncMock, return_value=(True, 4250)), \
             patch("main.record_user_transaction", new_callable=AsyncMock), \
             patch("main.add_to_abu_fund", new_callable=AsyncMock), \
             patch("main.spawn_task"), \
             patch("banner_manager.send_banner_message", new_callable=AsyncMock) as mock_send_banner, \
             patch("random.random", return_value=0.10), \
             patch("random.choices", return_value=["legendary_fake"]):
            await main.cmd_dossier(msg, board_id="b")
            caption = mock_send_banner.call_args.kwargs["caption"]
            for badge in ["МАЙОР-007", "ДУРКА-03", "СЛОНИК-777", "КОТ-МЯУ", "ABU-001", "CHAD-2077"]:
                if badge in caption:
                    captured_badges.add(badge)

    assert len(captured_badges) == 6, f"Not all badges captured: {captured_badges}"
