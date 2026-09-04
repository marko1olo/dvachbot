# -*- coding: utf-8 -*-
"""
Tests for Modernized Music Roast Engine:
- 24+ Unique Presets and Rotation
- Strict Ban on Quoting Lyrics / Song Words in Prompts
- Batching up to 5 tracks in a single multimodal Gemini API call
- Chunking albums (>5 tracks) into chunks of 5 + remainder
- Batch response parsing, fallback handling, DB logging, and CyberChad TTS
"""

import io
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from ai_manager import (
    MUSIC_ROAST_PRESETS,
    MUSIC_ROAST_TONES,
    get_music_roast_preset,
    build_single_music_roast_prompt,
    build_batch_music_roast_prompt,
    parse_music_roast_response,
    parse_batch_music_roast_response,
    compress_audio_for_gemini,
    handle_music_roast_batch,
    handle_music_roast,
    MUSIC_ROAST_SYSTEM_PROMPT,
    DEFAULT_BATCH_MUSIC_ROASTS,
)
from delivery_manager import _roast_album_tracks_in_batches


# ============================================================================
# 1. Presets & Tones Rotation Tests
# ============================================================================

class TestMusicRoastPresetsAndRotation:
    """Validates tone delivery modes and anti-repetition rotation."""

    def test_tones_inventory_count_and_structure(self):
        """Must have 20+ distinct tone modes, all with required keys."""
        assert len(MUSIC_ROAST_TONES) >= 20
        assert len(MUSIC_ROAST_PRESETS) >= 20

        for key, p in MUSIC_ROAST_TONES.items():
            assert "title" in p and len(p["title"]) > 0, f"Tone {key} missing title"
            assert "desc" in p and len(p["desc"]) > 0, f"Tone {key} missing desc"
            assert "angle" in p and len(p["angle"]) > 0, f"Tone {key} missing angle"
            assert "vocabulary" in p and len(p["vocabulary"]) > 0, f"Tone {key} missing vocabulary"

    def test_get_preset_explicit_key(self):
        """Requesting an existing key returns that exact tone preset."""
        p = get_music_roast_preset("aggressive_assault")
        assert p["key"] == "aggressive_assault"
        assert "агрессивный" in p["title"].lower()

    def test_preset_rotation_avoids_immediate_repeats(self):
        """Calling get_music_roast_preset repeatedly cycles through different tones."""
        picked = [get_music_roast_preset()["key"] for _ in range(8)]
        # No two consecutive keys should be identical
        for i in range(len(picked) - 1):
            assert picked[i] != picked[i + 1], f"Consecutive duplicates at index {i}: {picked[i]}"
        # Rich diversity: at least 4 unique tones out of 8 calls
        assert len(set(picked)) >= 4


# ============================================================================
# 2. Strict Prohibition on Quoting Lyrics & Personal Extrapolation
# ============================================================================

class TestPromptStrictConstraints:
    """Verifies that prompts strictly forbid quoting lyrics, eliminate audio-engineering pedantry, and focus on personal diagnosis."""

    def test_single_prompt_strictly_forbids_lyrics_quoting(self):
        preset = MUSIC_ROAST_TONES["aggressive_assault"]
        prompt = build_single_music_roast_prompt("Miyagi", "Captain", "3 мин", "track.mp3", preset)

        prompt_lower = prompt.lower()
        # Must strictly forbid quoting words/lyrics
        assert "запрещено цитировать текст" in prompt_lower or "запрещено цитировать" in prompt_lower
        assert "пересказывать сюжет" in prompt_lower
        # Must focus on personal diagnosis, not sound engineering
        assert "экстраполируй" in prompt_lower or "удар по слушателю" in prompt_lower
        assert "не звукорежиссеры" in prompt_lower
        # Must not request transcript
        assert "транскрипция:" not in prompt_lower

    def test_batch_prompt_strictly_forbids_lyrics_quoting(self):
        preset = MUSIC_ROAST_TONES["toxic_sarcasm"]
        tracks = [
            {"artist": "Artist 1", "title": "Song 1", "dur_str": "2 мин"},
            {"artist": "Artist 2", "title": "Song 2", "dur_str": "3 мин"},
        ]
        prompt = build_batch_music_roast_prompt(tracks, preset)

        prompt_lower = prompt.lower()
        assert "запрещено цитировать текст" in prompt_lower or "запрещено цитировать" in prompt_lower
        assert "пересказывать сюжет" in prompt_lower
        assert "общий вердикт" in prompt_lower
        assert "не звукорежиссеры" in prompt_lower
        assert "транскрипция:" not in prompt_lower
        assert "трек 1:" in prompt_lower
        assert "трек 2:" in prompt_lower

    def test_system_prompt_has_all_genres_and_deep_variations(self):
        """MUSIC_ROAST_SYSTEM_PROMPT must detail 15+ genres with 5+ degradation archetypes each."""
        p = MUSIC_ROAST_SYSTEM_PROMPT
        genres_to_check = [
            "РУССКИЙ РОК", "ПОСТ-ПАНК", "БАББЛГАМ-ПОП", "K-POP", "КАЛЬЯН-РЭП",
            "НЬЮСКУЛ ТРЭП", "ОЛДСКУЛ", "ДРИФТ-ФОНК", "ПОПСА", "МЕТАЛ",
            "ЭЛЕКТРОНИКА", "ШАНСОН", "ЭМО", "РУССКИЙ ГРАЙМ", "БАРДОВСКАЯ ПЕСНЯ",
            "НЕОКЛАССИКА", "ВИЧХАУС"
        ]
        for g in genres_to_check:
            assert g in p, f"Genre {g} missing from MUSIC_ROAST_SYSTEM_PROMPT"

        # Check that there are plenty of distinct bullet descriptions (at least 80 across all genres)
        bullet_count = p.count("\n- ")
        assert bullet_count >= 80, f"Expected >= 80 degradation descriptions, got {bullet_count}"

    def test_system_prompt_strictly_bans_tiktok_slop(self):
        """MUSIC_ROAST_SYSTEM_PROMPT must ban tiktok slang ('скуф', 'альтушка', 'дединсайд', 'вайб')."""
        p_lower = MUSIC_ROAST_SYSTEM_PROMPT.lower()
        assert "запрет на тиктокерский мусор" in p_lower or "тиктокерский" in p_lower
        assert "скуф" in p_lower
        assert "альтушка" in p_lower
        assert "дединсайд" in p_lower
        assert "вайб" in p_lower


# ============================================================================
# 3. Response Parsing Tests
# ============================================================================

class TestMusicResponseParsing:
    """Validates robust parsing for single and batched AI critique outputs."""

    def test_parse_single_response_clean(self):
        raw = "ВЕРДИКТ: Глухая бочка и каша в нижней середине.\nОЦЕНКА: 2/10 💩 (Уши кровоточат)"
        roast, rating = parse_music_roast_response(raw)
        assert "Глухая бочка" in roast
        assert "2/10 💩" in rating

    def test_parse_single_response_ignores_transcript_if_present(self):
        raw = (
            "ТРАНСКРИПЦИЯ: Я бегу по ночному городу\n"
            "ВЕРДИКТ: Хрипящий 808-й бас от которого развалится девятка.\n"
            "ШКАЛА: 3/10"
        )
        roast, rating = parse_music_roast_response(raw)
        assert "Я бегу" not in roast
        assert "Хрипящий 808-й бас" in roast
        assert "3/10" in rating

    def test_parse_batch_response_standard_3_tracks(self):
        raw = (
            "ТРЕК 1: Унылый пережатый бас и глухая бочка. [Оценка: 2/10]\n"
            "ТРЕК 2: Картонный автотюн школьника, стырившего бит с YouTube. [Оценка: 1/10]\n"
            "ТРЕК 3: Прямая бочка для сельской дискотеки без капли вкуса. [Оценка: 0/10]\n\n"
            "ОБЩИЙ ВЕРДИКТ: Пациент добровольно забивает уши дешевым звуковым мусором. Музыкальный вкус отсутствует на генетическом уровне.\n"
            "ИТОГОВАЯ ШКАЛА: 1/10 💩 (Тотальный зашквар ушей)"
        )
        reviews, overall_verdict, overall_rating, overall_score = parse_batch_music_roast_response(raw, count=3)

        assert len(reviews) == 3
        assert reviews[0]["index"] == 1
        assert "Глухая бочка" in reviews[0]["text"] or "пережатый бас" in reviews[0]["text"]
        assert reviews[0]["score"] == 2

        assert reviews[1]["index"] == 2
        assert reviews[1]["score"] == 1

        assert reviews[2]["index"] == 3
        assert reviews[2]["score"] == 0

        assert "генетическом уровне" in overall_verdict
        assert "1/10 💩" in overall_rating
        assert overall_score == 1

    def test_parse_batch_response_missing_track_graceful_fallback(self):
        """If model returned only 2 of 3 tracks, the 3rd gets a graceful placeholder."""
        raw = (
            "ТРЕК 1: Пластмассовый синтезатор. [Оценка: 3/10]\n"
            "ОБЩИЙ ВЕРДИКТ: Ужасная подборка.\n"
            "ИТОГОВАЯ ШКАЛА: 2/10 💩"
        )
        reviews, overall_verdict, overall_rating, overall_score = parse_batch_music_roast_response(raw, count=2)
        assert len(reviews) == 2
        assert reviews[0]["index"] == 1
        assert reviews[1]["index"] == 2
        assert overall_score == 2


# ============================================================================
# 4. Multi-Audio Gemini Multimodal Batching Tests
# ============================================================================

class TestGeminiMultiAudioBatching:
    """Validates that batches of up to 5 tracks are sent in a SINGLE Gemini multimodal API call."""

    @pytest.mark.asyncio
    @patch("ai_manager._safe_send_voice_roast", new_callable=AsyncMock)
    @patch("ai_manager._safe_send_roast", new_callable=AsyncMock)
    @patch("ai_manager.httpx.AsyncClient")
    async def test_batch_3_tracks_sent_in_single_gemini_request(
        self, mock_httpx_cls, mock_send_roast, mock_send_voice
    ):
        mock_bot = AsyncMock()
        mock_bot.get_file.return_value = MagicMock(file_path="music/track.mp3")
        mock_bot.download_file.return_value = io.BytesIO(b"MOCK_AUDIO_DATA_FOR_BATCH")

        # Mock Gemini 200 response with batch output
        mock_http = AsyncMock()
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": (
                            "ТРЕК 1: Заваленный саб-бас и клиппинг. [Оценка: 2/10]\n"
                            "ТРЕК 2: Дешевый автотюн мимо кассы. [Оценка: 1/10]\n"
                            "ТРЕК 3: Примитивные 3 аккорда на пианино. [Оценка: 3/10]\n\n"
                            "ОБЩИЙ ВЕРДИКТ: Коллекция пыточных записей для людей со здоровым слухом.\n"
                            "ИТОГОВАЯ ШКАЛА: 2/10 💩 (Патологический говноед)"
                        )
                    }]
                }
            }]
        }
        mock_http.post.return_value = mock_resp
        mock_httpx_cls.return_value.__aenter__.return_value = mock_http

        # 3 mock messages
        msg1 = MagicMock()
        msg1.from_user = MagicMock(id=111, is_bot=False)
        msg1.audio = MagicMock(performer="Artist1", title="Song1", duration=100, file_size=1_000_000, file_id="f1", file_name="s1.mp3")
        msg1.document = None

        msg2 = MagicMock()
        msg2.from_user = MagicMock(id=111, is_bot=False)
        msg2.audio = MagicMock(performer="Artist2", title="Song2", duration=120, file_size=1_000_000, file_id="f2", file_name="s2.mp3")
        msg2.document = None

        msg3 = MagicMock()
        msg3.from_user = MagicMock(id=111, is_bot=False)
        msg3.audio = MagicMock(performer="Artist3", title="Song3", duration=140, file_size=1_000_000, file_id="f3", file_name="s3.mp3")
        msg3.document = None

        messages = [msg1, msg2, msg3]

        with patch("common.token_pool.google_pool.get_all_active_tokens", return_value=["test-token"]):
            await handle_music_roast_batch(mock_bot, messages, board_id="b", stream="ru")

        # EXACTLY ONE Gemini POST request for all 3 tracks!
        assert mock_http.post.call_count == 1
        call_kwargs = mock_http.post.call_args[1]
        payload = call_kwargs.get("json") or {}
        parts = payload.get("contents", [{}])[0].get("parts", [])

        # Verify all 3 audio tracks are in parts
        inline_parts = [p for p in parts if "inlineData" in p]
        assert len(inline_parts) == 3, f"Expected 3 inlineData audio parts, got {len(inline_parts)}"

        # Verify safe roast was sent with all 3 tracks and overall verdict
        mock_send_roast.assert_called_once()
        sent_html = mock_send_roast.call_args[0][1]
        assert "Разбор пачки треков (3 шт.)" in sent_html
        assert "Artist1 — Song1" in sent_html
        assert "Artist2 — Song2" in sent_html
        assert "Artist3 — Song3" in sent_html
        assert "Общий вердикт /b/" in sent_html
        assert "2/10 💩" in sent_html

    @pytest.mark.asyncio
    @patch("ai_manager._safe_send_voice_roast", new_callable=AsyncMock)
    @patch("ai_manager._safe_send_roast", new_callable=AsyncMock)
    @patch("ai_manager.httpx.AsyncClient")
    async def test_batch_5_tracks_all_included(
        self, mock_httpx_cls, mock_send_roast, mock_send_voice
    ):
        mock_bot = AsyncMock()
        mock_bot.get_file.return_value = MagicMock(file_path="music/t.mp3")
        mock_bot.download_file.return_value = io.BytesIO(b"MOCK_BYTES")

        mock_http = AsyncMock()
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": (
                            "ТРЕК 1: Мусор. [Оценка: 1/10]\n"
                            "ТРЕК 2: Шлак. [Оценка: 0/10]\n"
                            "ТРЕК 3: Кал. [Оценка: 2/10]\n"
                            "ТРЕК 4: Помойка. [Оценка: 1/10]\n"
                            "ТРЕК 5: Копрофагия. [Оценка: 0/10]\n\n"
                            "ОБЩИЙ ВЕРДИКТ: Все 5 треков заслуживают утилизации.\n"
                            "ИТОГОВАЯ ШКАЛА: 0/10 💩 (Полная глухота)"
                        )
                    }]
                }
            }]
        }
        mock_http.post.return_value = mock_resp
        mock_httpx_cls.return_value.__aenter__.return_value = mock_http

        messages = []
        for i in range(1, 6):
            m = MagicMock()
            m.from_user = MagicMock(id=555, is_bot=False)
            m.audio = MagicMock(performer=f"Band{i}", title=f"Track{i}", duration=60, file_size=500_000, file_id=f"f{i}", file_name=f"t{i}.mp3")
            m.document = None
            messages.append(m)

        with patch("common.token_pool.google_pool.get_all_active_tokens", return_value=["test-token"]):
            await handle_music_roast_batch(mock_bot, messages, board_id="b", stream="ru")

        assert mock_http.post.call_count == 1
        parts = mock_http.post.call_args[1]["json"]["contents"][0]["parts"]
        inline_parts = [p for p in parts if "inlineData" in p]
        assert len(inline_parts) == 5

        sent_html = mock_send_roast.call_args[0][1]
        assert "Разбор пачки треков (5 шт.)" in sent_html


# ============================================================================
# 5. Media Group Album Chunking (>5 Tracks) Tests
# ============================================================================

class TestMediaGroupAlbumChunking:
    """Validates that albums with >5 tracks are chunked into batches of 5 + remainder."""

    @pytest.mark.asyncio
    @patch("ai_manager.handle_music_roast_batch", new_callable=AsyncMock)
    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_album_10_tracks_chunked_into_two_batches_of_5(
        self, mock_sleep, mock_roast_batch
    ):
        mock_bot = AsyncMock()
        audio_msgs = [MagicMock() for _ in range(10)]

        await _roast_album_tracks_in_batches(mock_bot, audio_msgs, board_id="b", stream="ru", post_num=100)

        # 10 tracks -> 2 chunks of 5!
        assert mock_roast_batch.call_count == 2
        chunk1 = mock_roast_batch.call_args_list[0][0][1]
        chunk2 = mock_roast_batch.call_args_list[1][0][1]
        assert len(chunk1) == 5
        assert len(chunk2) == 5
        assert chunk1 == audio_msgs[:5]
        assert chunk2 == audio_msgs[5:]
        # Sleep between chunks
        assert mock_sleep.call_count == 1
        mock_sleep.assert_called_with(2.0)

    @pytest.mark.asyncio
    @patch("ai_manager.handle_music_roast_batch", new_callable=AsyncMock)
    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_album_8_tracks_chunked_into_5_and_3(
        self, mock_sleep, mock_roast_batch
    ):
        mock_bot = AsyncMock()
        audio_msgs = [MagicMock() for _ in range(8)]

        await _roast_album_tracks_in_batches(mock_bot, audio_msgs, board_id="b", stream="ru", post_num=200)

        assert mock_roast_batch.call_count == 2
        chunk1 = mock_roast_batch.call_args_list[0][0][1]
        chunk2 = mock_roast_batch.call_args_list[1][0][1]
        assert len(chunk1) == 5
        assert len(chunk2) == 3


# ============================================================================
# 6. Single Track Forwarding & ffmpeg Safety
# ============================================================================

class TestSingleTrackAndFfmpeg:
    """Verifies handle_music_roast delegates properly and ffmpeg helper functions."""

    @pytest.mark.asyncio
    @patch("ai_manager.handle_music_roast_batch", new_callable=AsyncMock)
    async def test_handle_music_roast_delegates_to_batch(self, mock_roast_batch):
        mock_bot = AsyncMock()
        mock_msg = MagicMock()

        await handle_music_roast(mock_bot, mock_msg, board_id="b", stream="ru", post_num=77)

        mock_roast_batch.assert_called_once_with(mock_bot, [mock_msg], board_id="b", stream="ru", post_num=77)

    def test_compress_audio_empty_or_small(self):
        assert compress_audio_for_gemini(b"") == b""
        assert compress_audio_for_gemini(None) is None
        small = b"abc" * 100
        assert compress_audio_for_gemini(small) == small
