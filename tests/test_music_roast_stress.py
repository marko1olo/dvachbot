# -*- coding: utf-8 -*-
"""
Adversarial Stress Test Suite for DvachBot Music Auto-Roast Engine.
Empirically tests metadata edge cases, exotic formats, extreme unicode/durations,
STT cascade failure modes (Whisper + Gemini Audio), Telegram API errors,
and fallback resilience.
"""

import io
import math
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import httpx
from aiogram.exceptions import TelegramBadRequest

from ai_manager import (
    is_music_document,
    extract_music_metadata,
    format_music_duration,
    handle_music_roast,
    parse_music_roast_response,
    MUSIC_ROAST_SYSTEM_PROMPT,
    DEFAULT_MUSIC_ROASTS,
)
from common.html_utils import escape_html


# ============================================================================
# 1. Adversarial Metadata & Format Extraction Stress Tests
# ============================================================================

class TestAdversarialMetadataExtraction:
    """Stress tests metadata extraction with extreme edge cases."""

    @pytest.mark.parametrize("artist_input,title_input,filename,expected_artist,expected_title", [
        # Unicode / CJK / Emojis
        ("初音ミク", "メルト (Melt)", "miku.mp3", "初音ミク", "メルト (Melt)"),
        ("🔥 DJ Трахтор 🚜", "Басы Качают [VIP Edit]", "track.mp3", "🔥 DJ Трахтор 🚜", "Басы Качают [VIP Edit]"),
        ("موسيقى عربية", "عنوان الأغنية", "arabic.mp3", "موسيقى عربية", "عنوان الأغنية"),
        ("Z̸̡̢A̴̢L̴̡G̷O̶", "C̴̡O̷R̸R̶U̵P̶T̶", "zalgo.mp3", "Z̸̡̢A̴̢L̴̡G̷O̶", "C̴̡O̷R̸R̶U̵P̶T̶"),
        # Null-like / Whitespace-only strings
        ("   ", "   ", "Artist - Real Title.mp3", "Artist", "Real Title"),
        ("\t\n", "\r\n", "plain_title.mp3", "Неизвестный исполнитель", "plain_title"),
        (None, None, "   ", "Неизвестный исполнитель", "Без названия"),
        (None, None, "", "Неизвестный исполнитель", "Без названия"),
        (None, None, "   -   .mp3", "Неизвестный исполнитель", "   -   "),
    ])
    def test_unicode_and_blank_metadata(self, artist_input, title_input, filename, expected_artist, expected_title):
        """Validates handling of Unicode, CJK, RTL, emojis, and whitespace-only tags."""
        mock_msg = MagicMock()
        mock_msg.audio = MagicMock(
            performer=artist_input,
            title=title_input,
            file_name=filename,
            duration=120,
            file_size=1024,
            file_id="audio_unicode_1",
            mime_type="audio/mpeg"
        )
        mock_msg.document = None

        meta = extract_music_metadata(mock_msg)
        assert meta["artist"] == expected_artist
        assert meta["title"] == expected_title

    @pytest.mark.parametrize("filename,expected_artist,expected_title", [
        # Bracket release tags with various hyphens (hyphen-minus, en-dash, em-dash)
        ("[FLAC] [2024] [320kbps] Slipknot - Psychosocial.mp3", "Slipknot", "Psychosocial"),
        ("[OST] NieR: Automata – Weight of the World.flac", "NieR: Automata", "Weight of the World"),
        ("[Remastered] Queen — Bohemian Rhapsody.ogg", "Queen", "Bohemian Rhapsody"),
        ("Pink Floyd - Shine On You Crazy Diamond (Pts. 1-5).m4a", "Pink Floyd", "Shine On You Crazy Diamond (Pts. 1-5)"),
        ("Artist-Without-Spaces - Title.mp3", "Artist-Without-Spaces", "Title"),
        ("Artist - Title - Extra - Subtitle.mp3", "Artist", "Title - Extra - Subtitle"),
        ("SingleWordTitle.wav", "Неизвестный исполнитель", "SingleWordTitle"),
        ("01. Track Without Dash.mp3", "Неизвестный исполнитель", "01. Track Without Dash"),
        ("A" * 2000 + " - " + "B" * 2000 + ".mp3", "A" * 2000, "B" * 2000),
    ])
    def test_complex_filename_regex_parsing(self, filename, expected_artist, expected_title):
        """Stress-tests filename parsing against complex brackets, multi-hyphens, huge filenames."""
        mock_msg = MagicMock()
        mock_msg.audio = None
        mock_msg.document = MagicMock(
            file_name=filename,
            mime_type="audio/flac",
            file_size=5_000_000,
            file_id="doc_regex_01"
        )

        meta = extract_music_metadata(mock_msg)
        assert meta["artist"] == expected_artist
        assert meta["title"] == expected_title

    @pytest.mark.parametrize("duration_val,expected_str", [
        (0, "время не указано"),
        (-1, "время не указано"),
        (-99999, "время не указано"),
        (None, "время не указано"),
        ("invalid", "время не указано"),
        (float("nan"), "время не указано"),
        (3600, "60 мин"),
        (3665, "61 мин 5 сек"),
        (86400, "1440 мин"),
        ("125", "2 мин 5 сек"),
        (59.9, "время не указано" if int(59.9) <= 0 else "59 сек"),
    ])
    def test_adversarial_duration_formatting(self, duration_val, expected_str):
        """Validates duration formatting against negative, non-numeric, huge, or NaN values."""
        assert format_music_duration(duration_val) == expected_str

    @pytest.mark.parametrize("file_name,mime_type,is_music", [
        ("track.aiff", "audio/aiff", True),
        ("song.alac", "audio/alac", True),
        ("audio.wma", "audio/x-ms-wma", True),
        ("sample.opus", "audio/opus", True),
        ("TRACK.MP3", "APPLICATION/OCTET-STREAM", True),
        ("music.OGG", "application/ogg", True),
        ("sound.WAV", "audio/x-wav", True),
        ("flac_audio", "application/x-flac", True),
        ("doc_no_ext", "audio/mpeg", True),
        ("video.mp4", "video/mp4", False),
        ("image.png", "image/png", False),
        ("archive.tar.gz", "application/gzip", False),
        (None, None, False),
    ])
    def test_is_music_document_exotic_and_edge_types(self, file_name, mime_type, is_music):
        """Verifies exotic audio extensions and MIME types detection."""
        mock_doc = MagicMock()
        mock_doc.file_name = file_name
        mock_doc.mime_type = mime_type

        assert is_music_document(mock_doc) is is_music


# ============================================================================
# 2. Adversarial STT Cascade & Error Recovery Tests
# ============================================================================

class TestAdversarialSTTCascade:
    """Stress tests STT cascade: Whisper failures, Gemini failures, network issues, corrupted data."""

    @pytest.mark.asyncio
    @patch("ai_manager.httpx.AsyncClient")
    @patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
    async def test_stt_whisper_and_gemini_both_fail_graceful_instrumental_fallback(self, mock_summarize, mock_httpx_cls):
        """When Whisper times out AND Gemini throws 429/500, cascade falls back to instrumental marker without crashing."""
        mock_bot = AsyncMock()
        mock_bot.get_file.return_value = MagicMock(file_path="music/hardstyle.mp3")
        mock_bot.download_file.return_value = io.BytesIO(b"CORRUPTED_OR_RAW_AUDIO_BYTES")

        # Mock HTTP client where all endpoints fail
        mock_http = AsyncMock()
        mock_http.post.side_effect = httpx.ConnectError("Network unreachable")
        mock_httpx_cls.return_value.__aenter__.return_value = mock_http

        mock_summarize.return_value = (
            "Очередная долбежка по ушам без намека на мелодию.\n\n"
            "Шкала говноедства: 1/10 💩"
        )

        mock_msg = MagicMock()
        mock_msg.audio = MagicMock(
            performer="Headhunterz",
            title="Dragonborn",
            duration=210,
            file_size=6_000_000,
            file_id="audio_fail_01",
            file_name="dragonborn.mp3"
        )
        mock_msg.document = None
        mock_msg.reply = AsyncMock()

        with patch("common.token_pool.groq_pool.get_all_active_tokens", return_value=["groq-tok-1"]), \
             patch("common.token_pool.google_pool.get_all_active_tokens", return_value=["goog-tok-1"]):
            await handle_music_roast(mock_bot, mock_msg, board_id="b", stream="ru")

        # Ensure bot replied successfully with instrumental fallback
        mock_msg.reply.assert_called_once()
        reply_text = mock_msg.reply.call_args[0][0]
        assert "[Инструментальный трек / неразборчивый вокал]" in reply_text
        assert "Headhunterz — Dragonborn" in reply_text
        assert "Шкала говноедства:" in reply_text

    @pytest.mark.asyncio
    @patch("ai_manager.httpx.AsyncClient")
    @patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
    async def test_stt_whisper_returns_malformed_json(self, mock_summarize, mock_httpx_cls):
        """When Whisper returns 200 with invalid JSON, Gemini fallback is triggered."""
        mock_bot = AsyncMock()
        mock_bot.get_file.return_value = MagicMock(file_path="music/track.mp3")
        mock_bot.download_file.return_value = io.BytesIO(b"VALID_AUDIO_BYTES")

        mock_http = AsyncMock()
        mock_resp_groq = MagicMock(status_code=200)
        mock_resp_groq.json.side_effect = ValueError("Malformed JSON from proxy")

        mock_resp_gemini = MagicMock(status_code=200)
        mock_resp_gemini.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{"text": "Текст спасен через Gemini fallback"}]
                }
            }]
        }

        async def post_dispatcher(url, *args, **kwargs):
            if "googleapis.com" in str(url):
                return mock_resp_gemini
            return mock_resp_groq

        mock_http.post.side_effect = post_dispatcher
        mock_httpx_cls.return_value.__aenter__.return_value = mock_http

        mock_summarize.return_value = "Рецензия на трек.\n\nШкала говноедства: 0/10 💩"

        mock_msg = MagicMock()
        mock_msg.audio = MagicMock(
            performer="Artist",
            title="Track",
            duration=90,
            file_size=2_000_000,
            file_id="audio_json_err",
            file_name="track.mp3"
        )
        mock_msg.document = None
        mock_msg.reply = AsyncMock()

        with patch("common.token_pool.google_pool.get_all_active_tokens", return_value=["goog-key"]):
            await handle_music_roast(mock_bot, mock_msg, board_id="b", stream="ru")

        mock_msg.reply.assert_called_once()
        reply_text = mock_msg.reply.call_args[0][0]
        assert "Текст спасен через Gemini fallback" in reply_text

    @pytest.mark.asyncio
    @patch("ai_manager.httpx.AsyncClient")
    @patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
    async def test_stt_gemini_returns_empty_parts_or_silence(self, mock_summarize, mock_httpx_cls):
        """When Gemini returns '[Тишина]' or empty candidate list, fallback to instrumental marker."""
        mock_bot = AsyncMock()
        mock_bot.get_file.return_value = MagicMock(file_path="music/ambient.mp3")
        mock_bot.download_file.return_value = io.BytesIO(b"AMBIENT_BYTES")

        mock_http = AsyncMock()
        # Whisper returns 500
        mock_resp_groq = MagicMock(status_code=500)
        # Gemini returns [Инструментал]
        mock_resp_gemini = MagicMock(status_code=200)
        mock_resp_gemini.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "[Инструментал]"}]}}]
        }

        async def post_dispatcher(url, *args, **kwargs):
            if "googleapis.com" in str(url):
                return mock_resp_gemini
            return mock_resp_groq

        mock_http.post.side_effect = post_dispatcher
        mock_httpx_cls.return_value.__aenter__.return_value = mock_http

        mock_summarize.return_value = "Шум ветра и ничего больше.\n\nШкала говноедства: 5/10 💩"

        mock_msg = MagicMock()
        mock_msg.audio = MagicMock(
            performer="Brian Eno",
            title="Ambient 1",
            duration=300,
            file_size=10_000_000,
            file_id="ambient_01",
            file_name="ambient.mp3"
        )
        mock_msg.document = None
        mock_msg.reply = AsyncMock()

        with patch("common.token_pool.google_pool.get_all_active_tokens", return_value=["goog-key"]):
            await handle_music_roast(mock_bot, mock_msg, board_id="b", stream="ru")

        mock_msg.reply.assert_called_once()
        reply_text = mock_msg.reply.call_args[0][0]
        assert "[Инструментальный трек / неразборчивый вокал]" in reply_text
        assert "Brian Eno — Ambient 1" in reply_text


# ============================================================================
# 3. Adversarial Telegram Bot API & AI Generation Failure Tests
# ============================================================================

class TestAdversarialAPIFailures:
    """Tests resilience against Telegram API exceptions, AI summarizer failure, long messages."""

    @pytest.mark.asyncio
    @patch("ai_manager.summarize_text_with_hf", side_effect=RuntimeError("AI backend cluster down"))
    async def test_ai_summarizer_crash_uses_default_roast(self, mock_summarize):
        """When AI summarizer raises RuntimeError, DEFAULT_MUSIC_ROASTS provides fallback without crashing."""
        mock_bot = AsyncMock()
        mock_bot.get_file.return_value = MagicMock(file_path="music/test.mp3")
        mock_bot.download_file.return_value = io.BytesIO(b"AUDIO")

        mock_msg = MagicMock()
        mock_msg.audio = MagicMock(
            performer="Morgenshtern",
            title="Cadillac",
            duration=150,
            file_size=3_000_000,
            file_id="morg_01",
            file_name="cadillac.mp3"
        )
        mock_msg.document = None
        mock_msg.reply = AsyncMock()

        await handle_music_roast(mock_bot, mock_msg, board_id="b", stream="ru")

        mock_msg.reply.assert_called_once()
        reply_text = mock_msg.reply.call_args[0][0]
        assert "Morgenshtern — Cadillac" in reply_text
        assert "Шкала говноедства:" in reply_text
        # Must match one of the default fallback roasts
        assert any(fb[0] in reply_text for fb in DEFAULT_MUSIC_ROASTS)

    @pytest.mark.asyncio
    @patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
    async def test_telegram_message_too_long_handling(self, mock_summarize):
        """When Telegram returns 'message is too long', handle_music_roast retries with truncated text."""
        mock_bot = AsyncMock()
        mock_bot.get_file.return_value = MagicMock(file_path="music/long.mp3")
        mock_bot.download_file.return_value = io.BytesIO(b"AUDIO")

        mock_summarize.return_value = "Длинная рецензия " * 300 + "\n\nШкала говноедства: 0/10 💩"

        mock_msg = MagicMock()
        mock_msg.audio = MagicMock(
            performer="Artist",
            title="Song",
            duration=100,
            file_size=2_000_000,
            file_id="audio_long",
            file_name="song.mp3"
        )
        mock_msg.document = None

        # First reply call fails with 'message is too long', second call succeeds
        mock_msg.reply = AsyncMock(side_effect=[
            TelegramBadRequest(method=MagicMock(), message="Bad Request: message is too long"),
            MagicMock()
        ])

        await handle_music_roast(mock_bot, mock_msg, board_id="b", stream="ru")

        assert mock_msg.reply.call_count == 2
        truncated_call_arg = mock_msg.reply.call_args_list[1][0][0]
        assert len(truncated_call_arg) < 4000
        assert "Artist — Song" in truncated_call_arg

    @pytest.mark.parametrize("unsafe_raw", [
        "<script>fetch('http://evil.com')</script>",
        "<b onmouseover=alert(1)>click</b>",
        "<b><i><u>unclosed tags",
        "Test & ' \" < > characters",
    ])
    def test_xss_and_html_injection_in_roast_parsing(self, unsafe_raw):
        """Ensures raw AI output with unescaped HTML or XSS tags is safely sanitized."""
        ai_resp = f"Рецензия: {unsafe_raw}\n\nШкала говноедства: 0/10 💩 ({unsafe_raw})"
        roast_text, rating = parse_music_roast_response(ai_resp)

        # parse_music_roast_response cleans HTML tags
        assert "<script>" not in roast_text
        assert "<script>" not in rating
        assert "<b onmouseover" not in roast_text
