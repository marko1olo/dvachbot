# -*- coding: utf-8 -*-
"""
Resilience, Cascade Fallback, and Audio Caching tests for Cyberchad TTS Engine (common/tts_engine.py).
Validates Edge-TTS slang sanitization, multi-tier fallback (Dmitry -> Safe -> Svetlana -> Brian -> gTTS),
production male voice guarantee via FFmpeg pitch-down DSP, and dual-layer audio caching.
"""

import asyncio
import io
import os
import shutil
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from common.tts_engine import (
    clean_tts_text,
    sanitize_for_edge_tts,
    synthesize_cyberchad_voice,
    synthesize_cyberchad_voice_with_meta,
    get_preset,
    clear_tts_cache,
    get_tts_cache_stats,
    _compute_cache_key,
    get_cached_audio,
    put_cached_audio,
    CYBERCHAD_PRESETS,
    CYBERCHAD_GTTS_FALLBACK_FILTER,
)


@pytest.fixture(autouse=True)
def clean_cache_before_and_after():
    clear_tts_cache()
    yield
    clear_tts_cache()


class TestTextSanitizationAndSlang:
    """Tests for markdown stripping, ampersand normalization, and 2ch slang hyphenation."""

    def test_markdown_and_xml_entities_cleaned(self):
        text = "### Заголовок\nТы **тупой** *омега*, вот тебе `код` и &amp; рок & ролл."
        cleaned = clean_tts_text(text)
        assert "#" not in cleaned
        assert "**" not in cleaned
        assert "*" not in cleaned
        assert "`" not in cleaned
        assert "&" not in cleaned
        assert "и рок и ролл" in cleaned

    def test_sanitize_for_edge_tts_slang_hyphenation(self):
        """Verifies that words triggering Edge-TTS dropouts are hyphenated."""
        phrase = "Анон на дваче за рофл словил кринж от киберчеда, сыч и омежка в шоке."
        sanitized = sanitize_for_edge_tts(phrase)
        assert "А-нон" in sanitized
        assert "два-че" in sanitized
        assert "ро-фл" in sanitized
        assert "кри-нж" in sanitized
        assert "кибер-чеда" in sanitized
        assert "сы-ч" in sanitized
        assert "омеж-ка" in sanitized

    def test_sanitize_preserves_casing(self):
        lower = sanitize_for_edge_tts("анон и киберчед")
        upper = sanitize_for_edge_tts("Анон и Киберчед")
        assert "а-нон" in lower
        assert "кибер-чед" in lower
        assert "А-нон" in upper
        assert "Кибер-чед" in upper

    def test_empty_or_symbols_only(self):
        assert clean_tts_text("🔥💩🤖🛸⚡") == ""
        assert clean_tts_text("   ... ??? ---   ") == ""
        assert sanitize_for_edge_tts("") == ""


class TestMultiTierCascadeResilience:
    """Tests for graceful cascading across all 5 synthesis tiers when failures occur."""

    @pytest.mark.asyncio
    async def test_tier1_primary_dmitry_success(self):
        """Tier 1: Primary voice with preset parameters succeeds on first attempt."""
        text = "Тестовая реплика для первого эшелона."
        preset = CYBERCHAD_PRESETS["classic"]

        with patch("edge_tts.Communicate") as mock_comm_cls:
            mock_comm = AsyncMock()
            mock_comm.save = AsyncMock()
            mock_comm_cls.return_value = mock_comm

            with patch("shutil.which", return_value="C:\\ffmpeg\\bin\\ffmpeg.exe"):
                with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
                    mock_proc = AsyncMock()
                    mock_proc.communicate.return_value = (b"", b"")
                    mock_exec.return_value = mock_proc

                    with patch("os.path.exists", return_value=True), \
                         patch("os.path.getsize", return_value=5000), \
                         patch("builtins.open", MagicMock(return_value=io.BytesIO(b"MOCK_OGG_TIER1"))):

                        data, used_preset = await synthesize_cyberchad_voice_with_meta(text, preset="classic")
                        assert data == b"MOCK_OGG_TIER1"
                        assert used_preset.key == "classic"
                        # Called with primary voice and preset rate/pitch
                        mock_comm_cls.assert_called_once()
                        _, args, kwargs = mock_comm_cls.mock_calls[0]
                        assert args[1] == "ru-RU-DmitryNeural"
                        assert kwargs["rate"] == preset.rate
                        assert kwargs["pitch"] == preset.pitch

    @pytest.mark.asyncio
    async def test_tier2_dmitry_safe_mode_on_tier1_failure(self):
        """Tier 2: When Tier 1 raises NoAudioReceived, Tier 2 falls back to Dmitry with safe +0Hz pitch."""
        text = "Тест перехода на второй эшелон."

        with patch("edge_tts.Communicate") as mock_comm_cls:
            mock_comm_fail = AsyncMock()
            mock_comm_fail.save = AsyncMock(side_effect=RuntimeError("No audio was received"))

            mock_comm_ok = AsyncMock()
            mock_comm_ok.save = AsyncMock()

            # 1st call fails, 2nd call succeeds
            mock_comm_cls.side_effect = [mock_comm_fail, mock_comm_ok]

            with patch("shutil.which", return_value="C:\\ffmpeg\\bin\\ffmpeg.exe"):
                with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
                    mock_proc = AsyncMock()
                    mock_proc.communicate.return_value = (b"", b"")
                    mock_exec.return_value = mock_proc

                    with patch("os.path.exists", return_value=True), \
                         patch("os.path.getsize", return_value=5000), \
                         patch("builtins.open", MagicMock(return_value=io.BytesIO(b"MOCK_OGG_TIER2"))):

                        data, _ = await synthesize_cyberchad_voice_with_meta(text, preset="classic")
                        assert data == b"MOCK_OGG_TIER2"
                        assert mock_comm_cls.call_count == 2
                        # 2nd call used safe pitch +0Hz
                        call2_args = mock_comm_cls.call_args_list[1]
                        assert call2_args[0][1] == "ru-RU-DmitryNeural"
                        assert call2_args[1]["pitch"] == "+0Hz"

    @pytest.mark.asyncio
    async def test_tier3_svetlana_cyborg_pitch_down(self):
        """Tier 3: When Dmitry fails, Svetlana is used with FFmpeg cyborg pitch-down filter."""
        text = "Тест перехода на Светлану."

        with patch("edge_tts.Communicate") as mock_comm_cls:
            mock_fail = AsyncMock()
            mock_fail.save = AsyncMock(side_effect=RuntimeError("Dmitry cluster down"))

            mock_ok_svetlana = AsyncMock()
            mock_ok_svetlana.save = AsyncMock()

            # Attempts 1 & 2 fail, Attempt 3 (Svetlana) succeeds
            mock_comm_cls.side_effect = [mock_fail, mock_fail, mock_ok_svetlana]

            with patch("shutil.which", return_value="C:\\ffmpeg\\bin\\ffmpeg.exe"):
                with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
                    mock_proc = AsyncMock()
                    mock_proc.communicate.return_value = (b"", b"")
                    mock_exec.return_value = mock_proc

                    with patch("os.path.exists", return_value=True), \
                         patch("os.path.getsize", return_value=5000), \
                         patch("builtins.open", MagicMock(return_value=io.BytesIO(b"MOCK_CYBORG_OGG"))):

                        data, _ = await synthesize_cyberchad_voice_with_meta(text, preset="classic")
                        assert data == b"MOCK_CYBORG_OGG"
                        assert mock_comm_cls.call_count == 3
                        # Verify attempt 3 called Svetlana
                        assert mock_comm_cls.call_args_list[2][0][1] == "ru-RU-SvetlanaNeural"
                        # Verify FFmpeg applied the aggressive pitch-down cyborg filter for female voice
                        mock_exec.assert_called_once()
                        cmd_args = mock_exec.call_args[0]
                        assert CYBERCHAD_GTTS_FALLBACK_FILTER in cmd_args

    @pytest.mark.asyncio
    async def test_tier4_brian_multilingual(self):
        """Tier 4: When Russian voices fail, Brian Multilingual is used."""
        text = "Тест перехода на Брайана."

        with patch("edge_tts.Communicate") as mock_comm_cls:
            mock_fail = AsyncMock()
            mock_fail.save = AsyncMock(side_effect=RuntimeError("Ru voices down"))

            mock_ok_brian = AsyncMock()
            mock_ok_brian.save = AsyncMock()

            # Attempts 1, 2, 3 fail, Attempt 4 (Brian) succeeds
            mock_comm_cls.side_effect = [mock_fail, mock_fail, mock_fail, mock_ok_brian]

            with patch("shutil.which", return_value="C:\\ffmpeg\\bin\\ffmpeg.exe"):
                with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
                    mock_proc = AsyncMock()
                    mock_proc.communicate.return_value = (b"", b"")
                    mock_exec.return_value = mock_proc

                    with patch("os.path.exists", return_value=True), \
                         patch("os.path.getsize", return_value=5000), \
                         patch("builtins.open", MagicMock(return_value=io.BytesIO(b"MOCK_BRIAN_OGG"))):

                        data, _ = await synthesize_cyberchad_voice_with_meta(text, preset="classic")
                        assert data == b"MOCK_BRIAN_OGG"
                        assert mock_comm_cls.call_count == 4
                        assert mock_comm_cls.call_args_list[3][0][1] == "en-US-BrianMultilingualNeural"

    @pytest.mark.asyncio
    async def test_tier5_gtts_in_production_pitch_shifted(self):
        """Tier 5: When all Edge-TTS tiers fail, gTTS is NOT blocked in production and is pitched down."""
        text = "Тест резервного синтеза через gTTS с фильтром Киберчеда."

        # Simulate production environment (not in pytest env)
        with patch.dict(os.environ, {"PYTEST_CURRENT_TEST": ""}):
            with patch("edge_tts.Communicate", side_effect=RuntimeError("Total Edge Outage")):
                with patch("gtts.gTTS") as mock_gtts_cls:
                    mock_gtts = MagicMock()
                    mock_gtts_cls.return_value = mock_gtts

                    with patch("shutil.which", return_value="C:\\ffmpeg\\bin\\ffmpeg.exe"):
                        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
                            mock_proc = AsyncMock()
                            mock_proc.communicate.return_value = (b"", b"")
                            mock_exec.return_value = mock_proc

                            with patch("os.path.exists", return_value=True), \
                                 patch("os.path.getsize", return_value=4000), \
                                 patch("builtins.open", MagicMock(return_value=io.BytesIO(b"MOCK_GTTS_CYBORG_OGG"))):

                                data, _ = await synthesize_cyberchad_voice_with_meta(text, allow_female_fallback=True)
                                assert data == b"MOCK_GTTS_CYBORG_OGG"
                                mock_gtts_cls.assert_called_once()
                                # Verify FFmpeg applied pitch-down filter so female voice becomes deep male
                                mock_exec.assert_called_once()
                                cmd_args = mock_exec.call_args[0]
                                assert CYBERCHAD_GTTS_FALLBACK_FILTER in cmd_args

    @pytest.mark.asyncio
    async def test_female_fallback_without_ffmpeg_suppressed(self):
        """Validates that if FFmpeg is missing during gTTS fallback, raw female voice is suppressed."""
        text = "Тест подавления женского голоса без ffmpeg."

        with patch("edge_tts.Communicate", side_effect=RuntimeError("Edge Outage")):
            with patch("gtts.gTTS"):
                with patch("shutil.which", return_value=None):
                    with patch("os.path.exists", return_value=True), \
                         patch("os.path.getsize", return_value=4000):

                        # Because FFmpeg is absent, pitch-down cannot occur; output must be suppressed
                        result = await synthesize_cyberchad_voice(text, allow_female_fallback=True)
                        assert result is None


class TestAudioCaching:
    """Tests for memory LRU and persistent disk audio caching."""

    @pytest.mark.asyncio
    async def test_memory_cache_hit_bypasses_synthesis(self):
        text = "Фраза для проверки кэширования."
        cache_key = _compute_cache_key(clean_tts_text(text), "classic", "ru-RU-DmitryNeural", True)

        # Pre-seed cache
        await put_cached_audio(cache_key, b"MOCK_PRESEEDED_CACHED_BYTES_1234567890")

        # synthesis should return cached bytes immediately without calling edge_tts or ffmpeg
        with patch("edge_tts.Communicate") as mock_comm:
            data, preset = await synthesize_cyberchad_voice_with_meta(text, preset="classic", apply_dsp=True)
            assert data == b"MOCK_PRESEEDED_CACHED_BYTES_1234567890"
            assert preset.key == "classic"
            mock_comm.assert_not_called()

    @pytest.mark.asyncio
    async def test_disk_cache_loads_after_memory_cleared(self):
        text = "Фраза для проверки дискового кэша."
        cache_key = _compute_cache_key(clean_tts_text(text), "heavy_bass", "ru-RU-DmitryNeural", True)

        # Put into cache
        await put_cached_audio(cache_key, b"MOCK_DISK_CACHED_BYTES_ABCDEF123456")

        # Clear memory LRU cache only
        from common.tts_engine import _AUDIO_MEMORY_CACHE
        _AUDIO_MEMORY_CACHE.clear()
        assert len(_AUDIO_MEMORY_CACHE) == 0

        # Retrieve should reload from disk into memory
        loaded = await get_cached_audio(cache_key)
        assert loaded == b"MOCK_DISK_CACHED_BYTES_ABCDEF123456"
        assert len(_AUDIO_MEMORY_CACHE) == 1

    def test_cache_stats_and_clearing(self):
        stats_initial = get_tts_cache_stats()
        assert stats_initial["memory_entries"] == 0

        clear_tts_cache()
        stats_after = get_tts_cache_stats()
        assert stats_after["memory_entries"] == 0
        assert stats_after["disk_entries"] == 0
