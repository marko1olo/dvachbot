# -*- coding: utf-8 -*-
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from help_text import generate_secondary_welcome_message
from common.board_config import BOARD_CONFIG
import main

@pytest.mark.asyncio
async def test_generate_secondary_welcome_message():
    msg_ru = generate_secondary_welcome_message(BOARD_CONFIG, lang="ru")
    assert "/b/" in msg_ru
    assert "/a/" in msg_ru
    assert "/settings" in msg_ru
    assert "/wallet" in msg_ru
    assert "/votemute" in msg_ru
    assert "@tgach_bot" in msg_ru
    assert "@tgchan_archive" in msg_ru

    msg_en = generate_secondary_welcome_message(BOARD_CONFIG, lang="en")
    assert "Essential Commands" in msg_en
    assert "/b/" in msg_en

@pytest.mark.asyncio
async def test_send_welcome_sequence_flow():
    mock_bot = AsyncMock()
    chat_id = 999888
    board_id = "b"

    with patch("banner_manager.send_banner_message", new_callable=AsyncMock) as mock_banner, \
         patch("asyncio.sleep", new_callable=AsyncMock):
        await main.send_welcome_sequence(mock_bot, chat_id, board_id, stream="ru")

        # 1. Verify Message 1 (Banner + Board Manifesto + Rules)
        assert mock_banner.called
        b_args, b_kwargs = mock_banner.call_args
        caption = b_kwargs.get("caption", "")
        assert "ТГАЧ" in caption
        assert "Анонимная имиджборда" in caption
        assert "Реинкарнация" not in caption
        assert "духот" not in caption.lower()
        assert "—" not in caption
        assert "Как здесь общаться" in caption
        assert "Пост в тред" in caption
        assert "Reply" in caption
        assert "Реакции" in caption
        assert "РПГ" not in caption

        # 2. Verify Message 2 (Catalog + Commands + Channels)
        assert mock_bot.send_message.called
        s_args, s_kwargs = mock_bot.send_message.call_args
        sec_text = s_kwargs.get("text", "")
        assert "/b/" in sec_text
        assert "/settings" in sec_text
        assert "/wallet" in sec_text
        assert "@tgach_bot" in sec_text
        assert "@tgchan_archive" in sec_text
        assert "—" not in sec_text
