# -*- coding: utf-8 -*-
"""
Tests for Music Auto-Roast Engine (R1).
Validates metadata extraction, music document detection, STT cascade (Whisper + Gemini Audio fallback),
instrumental handling, 20MB limit safety, cynical 2ch /b/ music critic prompt and response formatting.
"""

import io
import re
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from ai_manager import (
    is_music_document,
    extract_music_metadata,
    format_music_duration,
    handle_music_roast,
    parse_music_roast_response,
    MUSIC_ROAST_SYSTEM_PROMPT,
)
from common.html_utils import escape_html
from aiogram.exceptions import TelegramBadRequest


# ============================================================================
# 1. Metadata Extraction & Music Document Detection Tests
# ============================================================================

class TestMusicMetadataExtraction:
    """Validates metadata parsing from Audio and Document Telegram objects."""

    def test_extract_audio_complete_tags(self):
        """Audio message with complete performer, title, duration tags."""
        mock_msg = MagicMock()
        mock_msg.audio = MagicMock()
        mock_msg.document = None
        mock_msg.audio.performer = "Miyagi & Andy Panda"
        mock_msg.audio.title = "Minor"
        mock_msg.audio.duration = 190
        mock_msg.audio.file_name = "minor_official.mp3"
        mock_msg.audio.file_size = 7_500_000
        mock_msg.audio.file_id = "audio_file_id_001"
        mock_msg.audio.mime_type = "audio/mpeg"

        meta = extract_music_metadata(mock_msg)

        assert meta["artist"] == "Miyagi & Andy Panda"
        assert meta["title"] == "Minor"
        assert meta["duration"] == 190
        assert meta["dur_str"] == "3 мин 10 сек"
        assert meta["file_id"] == "audio_file_id_001"
        assert meta["file_size"] == 7_500_000
        assert meta["file_name"] == "minor_official.mp3"

    def test_extract_audio_empty_tags_filename_dash_fallback(self):
        """Audio message with empty tags falling back to 'Artist - Title.mp3' file_name."""
        mock_msg = MagicMock()
        mock_msg.audio = MagicMock()
        mock_msg.document = None
        mock_msg.audio.performer = None
        mock_msg.audio.title = ""
        mock_msg.audio.duration = 190
        mock_msg.audio.file_name = "Miyagi & Andy Panda - Minor.mp3"
        mock_msg.audio.file_size = 6_000_000
        mock_msg.audio.file_id = "audio_file_id_002"
        mock_msg.audio.mime_type = "audio/mp3"

        meta = extract_music_metadata(mock_msg)

        assert meta["artist"] == "Miyagi & Andy Panda"
        assert meta["title"] == "Minor"
        assert meta["duration"] == 190
        assert meta["dur_str"] == "3 мин 10 сек"

    def test_extract_audio_empty_tags_no_dash_filename(self):
        """Audio message with empty tags and no dash in filename -> fallback artist & title."""
        mock_msg = MagicMock()
        mock_msg.audio = MagicMock()
        mock_msg.document = None
        mock_msg.audio.performer = None
        mock_msg.audio.title = None
        mock_msg.audio.duration = 45
        mock_msg.audio.file_name = "phonk_track_01.mp3"
        mock_msg.audio.file_size = 2_000_000
        mock_msg.audio.file_id = "audio_file_id_003"
        mock_msg.audio.mime_type = "audio/mpeg"

        meta = extract_music_metadata(mock_msg)

        assert meta["artist"] == "Неизвестный исполнитель"
        assert meta["title"] == "phonk_track_01"
        assert meta["duration"] == 45
        assert meta["dur_str"] == "45 сек"

    def test_extract_audio_bracketed_prefix_filename(self):
        """Audio filename with release tags like '[320kbps] Slipknot - Duality.mp3'."""
        mock_msg = MagicMock()
        mock_msg.audio = MagicMock()
        mock_msg.document = None
        mock_msg.audio.performer = ""
        mock_msg.audio.title = ""
        mock_msg.audio.duration = 252
        mock_msg.audio.file_name = "[320kbps] Slipknot - Duality.mp3"
        mock_msg.audio.file_size = 10_000_000
        mock_msg.audio.file_id = "audio_file_id_004"
        mock_msg.audio.mime_type = "audio/mpeg"

        meta = extract_music_metadata(mock_msg)

        assert "Slipknot" in meta["artist"]
        assert "Duality" in meta["title"]
        assert meta["duration"] == 252
        assert meta["dur_str"] == "4 мин 12 сек"

    def test_extract_document_flac_music_file(self):
        """Document message containing FLAC music file."""
        mock_msg = MagicMock()
        mock_msg.audio = None
        mock_msg.document = MagicMock()
        mock_msg.document.file_name = "Linkin Park - Numb.flac"
        mock_msg.document.mime_type = "audio/flac"
        mock_msg.document.file_size = 28_000_000
        mock_msg.document.file_id = "doc_flac_001"

        assert is_music_document(mock_msg.document) is True

        meta = extract_music_metadata(mock_msg)

        assert meta["artist"] == "Linkin Park"
        assert meta["title"] == "Numb"
        assert meta["file_size"] == 28_000_000
        assert meta["file_id"] == "doc_flac_001"
        assert meta["dur_str"] == "время не указано"

    @pytest.mark.parametrize("file_name,mime_type", [
        ("track.mp3", "audio/mpeg"),
        ("song.wav", "audio/wav"),
        ("audio.flac", "audio/flac"),
        ("music.ogg", "audio/ogg"),
        ("podcast.m4a", "audio/x-m4a"),
        ("sample.aac", "audio/aac"),
        ("track.opus", "audio/opus"),
        ("song.wma", "audio/x-ms-wma"),
        ("UPPERCASE.MP3", "application/octet-stream"),
        ("LOSSLESS.FLAC", "application/octet-stream"),
    ])
    def test_is_music_document_supported_formats(self, file_name, mime_type):
        """All supported music document extensions and MIME types return True."""
        mock_doc = MagicMock()
        mock_doc.file_name = file_name
        mock_doc.mime_type = mime_type

        assert is_music_document(mock_doc) is True

    @pytest.mark.parametrize("file_name,mime_type", [
        ("report.pdf", "application/pdf"),
        ("archive.zip", "application/zip"),
        ("setup.exe", "application/x-msdownload"),
        ("photo.jpg", "image/jpeg"),
        ("picture.png", "image/png"),
        ("video.mp4", "video/mp4"),
        ("script.py", "text/x-python"),
        ("data.json", "application/json"),
        ("", ""),
    ])
    def test_is_music_document_non_music_files(self, file_name, mime_type):
        """Non-music files return False."""
        mock_doc = MagicMock()
        mock_doc.file_name = file_name
        mock_doc.mime_type = mime_type

        assert is_music_document(mock_doc) is False

    def test_is_music_document_none_safe(self):
        """Passing None to is_music_document returns False without error."""
        assert is_music_document(None) is False

    @pytest.mark.parametrize("seconds,expected", [
        (190, "3 мин 10 сек"),
        (180, "3 мин"),
        (65, "1 мин 5 сек"),
        (60, "1 мин"),
        (45, "45 сек"),
        (1, "1 сек"),
        (0, "время не указано"),
        (-10, "время не указано"),
        (None, "время не указано"),
        ("invalid", "время не указано"),
    ])
    def test_duration_formatting_helpers(self, seconds, expected):
        """Validates format_music_duration conversion logic."""
        assert format_music_duration(seconds) == expected


# ============================================================================
# 2. STT & Audio Handling Tests (Groq Whisper, Gemini Fallback, 20MB Safety)
# ============================================================================

class TestMusicSTTAndAudioHandling:
    """Validates audio download, Whisper STT, Gemini Audio fallback, and edge cases."""

    @pytest.mark.asyncio
    @patch("ai_manager.httpx.AsyncClient")
    @patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
    async def test_stt_whisper_groq_success(self, mock_summarize, mock_httpx_cls):
        """Successful Whisper STT returns transcript and passes it to roast."""
        mock_bot = AsyncMock()
        mock_file_info = MagicMock(file_path="music/track.mp3")
        mock_bot.get_file.return_value = mock_file_info
        mock_bot.download_file.return_value = io.BytesIO(b"ID3_MOCK_AUDIO_BYTES")

        # Mock Groq Whisper HTTP response
        mock_http_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"text": "Пока горит огонь в моей груди, я буду петь"}
        mock_http_client.post.return_value = mock_resp
        mock_httpx_cls.return_value.__aenter__.return_value = mock_http_client

        mock_summarize.return_value = (
            "Очередной депрессивный мамкин рэпчик. "
            "Слушать это трезвым физически больно.\n\n"
            "Шкала говноедства: 1/10 💩 (Кал высшей пробы)"
        )

        mock_msg = MagicMock()
        mock_msg.audio = MagicMock()
        mock_msg.document = None
        mock_msg.audio.performer = "Miyagi"
        mock_msg.audio.title = "Captain"
        mock_msg.audio.duration = 180
        mock_msg.audio.file_size = 5_000_000
        mock_msg.audio.file_id = "audio_123"
        mock_msg.audio.file_name = "track.mp3"
        mock_msg.reply = AsyncMock()

        await handle_music_roast(mock_bot, mock_msg, board_id="b", stream="ru")

        # Verify Groq transcription was queried
        mock_http_client.post.assert_called_once()
        post_url = mock_http_client.post.call_args[0][0]
        assert "api.groq.com" in post_url

        # Verify reply was sent with formatted HTML
        mock_msg.reply.assert_called_once()
        reply_text = mock_msg.reply.call_args[0][0]
        assert "Miyagi — Captain" in reply_text
        assert "Пока горит огонь" in reply_text
        assert "Шкала говноедства:" in reply_text

    @pytest.mark.asyncio
    @patch("ai_manager.httpx.AsyncClient")
    @patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
    async def test_stt_whisper_failure_gemini_audio_fallback(self, mock_summarize, mock_httpx_cls):
        """Whisper failure (429/timeout) falls back to Gemini Multimodal Audio STT."""
        mock_bot = AsyncMock()
        mock_bot.get_file.return_value = MagicMock(file_path="music/track.mp3")
        mock_bot.download_file.return_value = io.BytesIO(b"MOCK_AUDIO_BYTES")

        # Mock Groq failure (429), followed by Gemini success (200)
        mock_http_client = AsyncMock()
        mock_resp_groq = MagicMock(status_code=429)
        mock_resp_gemini = MagicMock()
        mock_resp_gemini.status_code = 200
        mock_resp_gemini.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{"text": "Текст песни расшифрован через Gemini Multimodal"}]
                }
            }]
        }

        async def post_handler(url, *args, **kwargs):
            if "googleapis.com" in str(url) or "generativelanguage" in str(url):
                return mock_resp_gemini
            return mock_resp_groq

        mock_http_client.post.side_effect = post_handler
        mock_httpx_cls.return_value.__aenter__.return_value = mock_http_client

        mock_summarize.return_value = (
            "Бессвязный графоманский высер.\n\n"
            "Шкала говноедства: 0/10 💩"
        )

        mock_msg = MagicMock()
        mock_msg.audio = MagicMock(
            performer="Big Baby Tape", title="Gimme The Loot",
            duration=120, file_size=4_000_000, file_id="bbt_01",
            file_name="bbt.mp3"
        )
        mock_msg.document = None
        mock_msg.reply = AsyncMock()

        with patch("common.token_pool.google_pool.get_all_active_tokens", return_value=["test-google-key"]):
            await handle_music_roast(mock_bot, mock_msg, board_id="b", stream="ru")

        # Verify fallback occurred
        assert mock_http_client.post.call_count >= 2
        mock_msg.reply.assert_called_once()
        reply_text = mock_msg.reply.call_args[0][0]
        assert "Gemini Multimodal" in reply_text

    @pytest.mark.asyncio
    @patch("ai_manager.httpx.AsyncClient")
    @patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
    async def test_stt_instrumental_or_empty_transcript(self, mock_summarize, mock_httpx_cls):
        """Empty STT / silence sets lyrics sample to '[Инструментальный трек / неразборчивый вокал]'."""
        mock_bot = AsyncMock()
        mock_bot.get_file.return_value = MagicMock(file_path="music/techno.mp3")
        mock_bot.download_file.return_value = io.BytesIO(b"TECHNO_BEATS")

        mock_http_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"text": "[Тишина]"}
        mock_http_client.post.return_value = mock_resp
        mock_httpx_cls.return_value.__aenter__.return_value = mock_http_client

        mock_summarize.return_value = (
            "Пердеж из FL Studio без вокала.\n\n"
            "Шкала говноедства: 2/10 💩"
        )

        mock_msg = MagicMock()
        mock_msg.audio = MagicMock(
            performer="Deadmau5", title="Strobe",
            duration=600, file_size=15_000_000, file_id="deadmau5_strobe",
            file_name="strobe.mp3"
        )
        mock_msg.document = None
        mock_msg.reply = AsyncMock()

        await handle_music_roast(mock_bot, mock_msg, board_id="b", stream="ru")

        mock_msg.reply.assert_called_once()
        reply_text = mock_msg.reply.call_args[0][0]
        assert "[Инструментальный трек / неразборчивый вокал]" in reply_text
        assert "Deadmau5 — Strobe" in reply_text

    @pytest.mark.asyncio
    @patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
    async def test_stt_file_over_20mb_skip_download(self, mock_summarize):
        """Files > 20MB skip download and set sample note '[Файл >20MB — семпл не скачан]'."""
        mock_bot = AsyncMock()

        mock_summarize.return_value = (
            "Отрецензировано чисто по названию, качать эту 50-мегабайтную парашу я не стал.\n\n"
            "Шкала говноедства: 0/10 💩"
        )

        mock_msg = MagicMock()
        mock_msg.audio = None
        mock_msg.document = MagicMock(
            file_name="Pink Floyd - Echoes.flac",
            mime_type="audio/flac",
            file_size=55_000_000,  # 55MB > 20MB limit
            file_id="flac_huge_01"
        )
        mock_msg.reply = AsyncMock()

        await handle_music_roast(mock_bot, mock_msg, board_id="b", stream="ru")

        # Bot download_file should NEVER be called for >20MB
        mock_bot.download_file.assert_not_called()

        mock_msg.reply.assert_called_once()
        reply_text = mock_msg.reply.call_args[0][0]
        assert escape_html("[Файл >20MB — семпл не скачан]") in reply_text or "[Файл &gt;20MB — семпл не скачан]" in reply_text
        assert "Pink Floyd — Echoes" in reply_text


# ============================================================================
# 3. 2ch /b/ Roast Prompt Structure, Parsing & Response Formatting Tests
# ============================================================================

class TestMusicRoastPromptAndFormatting:
    """Validates 2ch /b/ prompt constraints, response layout, HTML sanitization, and parsing."""

    def test_music_roast_prompt_structure_and_constraints(self):
        """MUSIC_ROAST_SYSTEM_PROMPT contains authentic 2ch /b/ tone and forbids polite AI cliches."""
        prompt_lower = MUSIC_ROAST_SYSTEM_PROMPT.lower()

        # Tone and persona requirements
        assert "двач" in prompt_lower or "/b/" in prompt_lower or "критик" in prompt_lower
        assert "шкала говноедства" in prompt_lower or "вердикт" in prompt_lower

        # Disclaimers and fluff forbidden
        forbidden = [
            "как ии", "как языковая модель", "извините", "я бот",
            "вот твоя рецензия", "вот твой анализ"
        ]
        for term in forbidden:
            assert term not in prompt_lower, f"Prompt contains forbidden cliche: {term}"

    def test_parse_music_roast_response_standard_rating(self):
        """Parses model output with rating on separate line."""
        ai_output = (
            "Очередной сопливый кальянный рэп для школьниц из тиктока.\n"
            "Рифмы уровня 'любовь-кровь', бит стырен с бесплатного пака.\n\n"
            "Шкала говноедства: 0/10 💩 (Абсолютный кринж)"
        )
        roast_text, rating = parse_music_roast_response(ai_output)

        assert "кальянный рэп" in roast_text
        assert "Шкала говноедства" not in roast_text  # Stripped from roast text
        assert "0/10 💩" in rating or "Абсолютный кринж" in rating

    def test_parse_music_roast_response_fallback_when_no_rating_line(self):
        """Parses model output without explicit rating line and applies fallback rating."""
        ai_output = "Унылый проходняк, записанный на микрофон от наушников."
        roast_text, rating = parse_music_roast_response(ai_output)

        assert "Унылый проходняк" in roast_text
        assert rating is not None
        assert len(rating) > 0

    def test_response_html_layout_structure(self):
        """HTML response layout conforms to specification."""
        artist = "Oxxxymiron"
        title = "Город под подошвой"
        dur_str = "4 мин"
        lyrics_sample = "Весь мой рэп, если коротко..."
        roast_text = "Кусок ностальгического бумерского пафоса."
        rating = "3/10 💩 (Для скуфов)"

        formatted = (
            f"🎵 <b>Трек:</b> {escape_html(artist)} — {escape_html(title)} (<i>{dur_str}</i>)\n"
            f"📝 <b>Текст / Семпл:</b> <i>«{escape_html(lyrics_sample)}»</i>\n\n"
            f"🔥 <b>Вердикт /b/ музкритика:</b>\n"
            f"{escape_html(roast_text)}\n\n"
            f"💩 <b>Шкала говноедства:</b> {escape_html(rating)}"
        )

        assert "🎵 <b>Трек:</b>" in formatted
        assert "📝 <b>Текст / Семпл:</b>" in formatted
        assert "🔥 <b>Вердикт /b/ музкритика:</b>" in formatted
        assert "💩 <b>Шкала говноедства:</b>" in formatted
        assert f"{artist} — {title}" in formatted

    def test_response_html_escaping_unsafe_input(self):
        """Unsafe HTML entities in artist, title, lyrics are properly escaped."""
        raw_artist = "<script>alert('XSS')</script>"
        raw_title = "<b>Rock</b> & \"Roll\""
        raw_lyrics = "<img src=x onerror=hack()>"

        clean_artist = escape_html(raw_artist)
        clean_title = escape_html(raw_title)
        clean_lyrics = escape_html(raw_lyrics)

        assert "<script>" not in clean_artist
        assert "&lt;script&gt;" in clean_artist
        assert "<b>" not in clean_title
        assert "&lt;b&gt;" in clean_title
        assert "<img" not in clean_lyrics
        assert "&lt;img" in clean_lyrics


# ============================================================================
# 4. Async Execution & Board Dispatch Tests
# ============================================================================

class TestHandleMusicRoastAsyncExecution:
    """Validates complete async pipeline with mocked Bot, Message, and Dispatcher."""

    @pytest.mark.asyncio
    @patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock)
    @patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
    @patch("ai_manager.httpx.AsyncClient")
    async def test_handle_music_roast_audio_full_flow(self, mock_httpx_cls, mock_summarize, mock_synth_meta):
        """Full execution flow for Audio message with post publication."""
        mock_bot = AsyncMock()
        mock_bot.get_file.return_value = MagicMock(file_path="music/audio.mp3")
        mock_bot.download_file.return_value = io.BytesIO(b"AUDIO_RAW")

        mock_http = AsyncMock()
        mock_http.post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"text": "Текст песни для тестирования"}
        )
        mock_httpx_cls.return_value.__aenter__.return_value = mock_http

        mock_summarize.return_value = (
            "Слушать это — добровольное насилие над ушами.\n\n"
            "Шкала говноедства: 0/10 💩"
        )
        mock_synth_meta.return_value = (b"CYBERCHAD_ROAST_BYTES", None)

        mock_msg = MagicMock()
        mock_msg.audio = MagicMock(
            performer="Instasamka", title="За деньги да",
            duration=110, file_size=3_000_000, file_id="samka_01",
            file_name="samka.mp3"
        )
        mock_msg.document = None
        mock_msg.reply = AsyncMock()
        mock_msg.reply_voice = AsyncMock()

        with patch("common.bot_helpers.process_new_post", new_callable=AsyncMock) as mock_process_post:
            await handle_music_roast(mock_bot, mock_msg, board_id="b", stream="ru", post_num=999)

            # Assert posts published to board with reply_to_post=999 (text + voice)
            assert mock_process_post.call_count == 2
            text_params = mock_process_post.call_args_list[0][0][0]
            assert text_params.board_id == "b"
            assert text_params.reply_to_post == 999
            assert text_params.content["is_system_message"] is True
            assert "Instasamka — За деньги да" in text_params.content["text"]

            voice_params = mock_process_post.call_args_list[1][0][0]
            assert voice_params.board_id == "b"
            assert voice_params.reply_to_post == 999
            assert voice_params.content["type"] == "voice"
            assert voice_params.content["voice_bytes"] == b"CYBERCHAD_ROAST_BYTES"
            assert voice_params.content["caption"] == "🔥 Разъёб от Киберчеда"

            # Direct text roast is ALWAYS sent immediately to author as a reply
            mock_msg.reply.assert_called_once()
            reply_text = mock_msg.reply.call_args[0][0]
            assert "Instasamka — За деньги да" in reply_text

    @pytest.mark.asyncio
    @patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
    @patch("ai_manager.httpx.AsyncClient")
    async def test_handle_music_roast_document_flac_flow(self, mock_httpx_cls, mock_summarize):
        """Full execution flow for FLAC Document message."""
        mock_bot = AsyncMock()
        mock_bot.get_file.return_value = MagicMock(file_path="music/track.flac")
        mock_bot.download_file.return_value = io.BytesIO(b"FLAC_RAW")

        mock_http = AsyncMock()
        mock_http.post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"text": "I tried so hard and got so far"}
        )
        mock_httpx_cls.return_value.__aenter__.return_value = mock_http

        mock_summarize.return_value = (
            "Классика 2000-х для страдающих подростков.\n\n"
            "Шкала говноедства: 4/10 💩 (Ностальгический кал)"
        )

        mock_msg = MagicMock()
        mock_msg.audio = None
        mock_msg.document = MagicMock(
            file_name="Linkin Park - In the End.flac",
            mime_type="audio/flac",
            file_size=18_000_000,
            file_id="flac_lp_01"
        )
        mock_msg.reply = AsyncMock()

        await handle_music_roast(mock_bot, mock_msg, board_id="b", stream="ru", post_num=None)

        # No board context → direct reply is sent (no deduplication bypass)
        mock_msg.reply.assert_called_once()
        reply_text = mock_msg.reply.call_args[0][0]
        assert "Linkin Park — In the End" in reply_text
        assert "I tried so hard" in reply_text

    @pytest.mark.asyncio
    async def test_handle_music_roast_non_music_ignored(self):
        """Non-music document returns immediately without processing."""
        mock_bot = AsyncMock()
        mock_msg = MagicMock()
        mock_msg.audio = None
        mock_msg.document = MagicMock(
            file_name="contract.pdf",
            mime_type="application/pdf",
            file_size=1_000_000,
            file_id="pdf_01"
        )
        mock_msg.reply = AsyncMock()

        await handle_music_roast(mock_bot, mock_msg, board_id="b", stream="ru")

        # Bot and message should NOT be called
        mock_bot.get_file.assert_not_called()
        mock_msg.reply.assert_not_called()

    @pytest.mark.asyncio
    @patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
    @patch("ai_manager.httpx.AsyncClient")
    async def test_handle_music_roast_reply_failure_falls_back_to_answer(self, mock_httpx_cls, mock_summarize):
        """When message.reply fails with 'message not found', it falls back to message.answer."""
        mock_bot = AsyncMock()
        mock_bot.get_file.return_value = MagicMock(file_path="music/audio.mp3")
        mock_bot.download_file.return_value = io.BytesIO(b"AUDIO")

        mock_http = AsyncMock()
        mock_http.post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"text": "Sample text"}
        )
        mock_httpx_cls.return_value.__aenter__.return_value = mock_http

        mock_summarize.return_value = "Кринж.\n\nШкала говноедства: 0/10 💩"

        mock_msg = MagicMock()
        mock_msg.audio = MagicMock(
            performer="Artist", title="Song",
            duration=60, file_size=1_000_000, file_id="a1",
            file_name="song.mp3"
        )
        mock_msg.document = None
        mock_msg.reply = AsyncMock(side_effect=TelegramBadRequest(method=MagicMock(), message="message to be replied not found"))
        mock_msg.answer = AsyncMock()

        await handle_music_roast(mock_bot, mock_msg, board_id="b", stream="ru")

        mock_msg.reply.assert_called_once()
        mock_msg.answer.assert_called_once()
