import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import io
import time

from broadcaster import _format_main_text
from ai_manager import (
    handle_music_roast_batch,
    MUSIC_ROAST_RATE_LIMIT,
    MUSIC_ROAST_RATE_WINDOW_SEC,
    MUSIC_ROAST_FLOOD_RESPONSES,
    _music_roast_user_times,
    _music_roast_seen_mg
)


def test_broadcaster_cyberchad_voice_post_never_duplicates_transcript():
    """Verify broadcaster._format_main_text formats voice posts as '🔥 Разъёб от Киберчеда' and never spoken transcript."""
    # 1. Standard Cyberchad voice post with caption
    content1 = {
        "type": "voice",
        "caption": "🔥 Разъёб от Киберчеда",
        "text": "Ты, кусок вонючего биомусора, включил это дерьмо на обоссанном диване...",
        "roast_text": "Ты, кусок вонючего биомусора, включил это дерьмо на обоссанном диване...",
        "is_cyberchad": True,
        "is_ai_roast": True
    }
    formatted1 = _format_main_text(content1)
    assert formatted1 == "🔥 Разъёб от Киберчеда"
    assert "биомусора" not in formatted1

    # 2. Cyberchad voice post without caption
    content2 = {
        "type": "voice",
        "text": "Ты, кусок вонючего биомусора...",
        "roast_text": "Ты, кусок вонючего биомусора...",
        "is_cyberchad": True
    }
    formatted2 = _format_main_text(content2)
    assert formatted2 == "🔥 Разъёб от Киберчеда"
    assert "биомусора" not in formatted2

    # 3. Regular non-cyberchad user post with text (should format text normally)
    content3 = {
        "type": "text",
        "text": "Обычный текст поста от анона"
    }
    formatted3 = _format_main_text(content3)
    assert "Обычный текст поста от анона" in formatted3


@pytest.mark.asyncio
async def test_music_roast_rate_limit_5_per_hour_rejects_6th_track_to_pm():
    """Verify limit of 5 music tracks per user per hour. The 6th track sends sarcastic reject to user PM and skips AI."""
    _music_roast_user_times.clear()
    _music_roast_seen_mg.clear()

    user_id = 777888
    assert MUSIC_ROAST_RATE_LIMIT == 5

    mock_bot = AsyncMock()
    mock_bot.get_file.return_value = MagicMock(file_path="music/track.mp3", file_size=1000)
    mock_bot.download_file.return_value = io.BytesIO(b"MOCK_AUDIO_DATA")

    def make_msg(idx):
        msg = MagicMock()
        msg.audio = MagicMock(
            performer=f"Artist {idx}",
            title=f"Track {idx}",
            duration=120,
            file_size=1000,
            file_id=f"audio_fid_{idx}",
            file_name=f"track_{idx}.mp3"
        )
        msg.document = None
        msg.from_user = MagicMock(id=user_id, is_bot=False)
        msg.is_system_message = False
        msg.caption = None
        msg.media_group_id = None
        return msg

    with patch("ai_manager.httpx.AsyncClient") as mock_httpx, \
         patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock) as mock_sum, \
         patch("common.token_pool.google_pool.get_all_active_tokens", return_value=["fake-key"]), \
         patch("common.bot_helpers.process_new_post", new_callable=AsyncMock) as mock_post:

        mock_http = AsyncMock()
        mock_http.post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "candidates": [{
                    "content": {
                        "parts": [{
                            "text": "ВЕРДИКТ: Нормальный трек.\nШКАЛА: 5/10"
                        }]
                    }
                }]
            }
        )
        mock_httpx.return_value.__aenter__.return_value = mock_http

        # Send 5 tracks sequentially -> all 5 must be processed
        for i in range(5):
            msg = make_msg(i + 1)
            await handle_music_roast_batch(mock_bot, [msg], board_id="b", stream="ru", post_num=100 + i)

        assert mock_http.post.call_count == 5
        assert len(_music_roast_user_times[user_id]) == 5

        # 6th track within the same hour -> must be blocked from AI roast
        msg6 = make_msg(6)
        mock_http.post.reset_mock()
        mock_bot.send_message.reset_mock()

        await handle_music_roast_batch(mock_bot, [msg6], board_id="b", stream="ru", post_num=106)

        # Gemini API must NOT be called for the 6th track
        mock_http.post.assert_not_called()

        # Sarcastic reject must be sent directly to user's PM (chat_id=user_id)
        mock_bot.send_message.assert_called_once()
        pm_call_kwargs = mock_bot.send_message.call_args[1]
        assert pm_call_kwargs["chat_id"] == user_id
        pm_text = pm_call_kwargs["text"]
        assert any(resp in pm_text for resp in MUSIC_ROAST_FLOOD_RESPONSES)
