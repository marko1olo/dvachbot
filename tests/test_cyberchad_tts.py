# -*- coding: utf-8 -*-
"""
Unit and integration tests for Cyberchad Cloud TTS & DSP Engine (common/tts_engine.py).
Validates text cleaning, preset registry, rate/pitch modulation, edge-tts synthesis,
ffmpeg DSP filters, gTTS fallback, and Telegram voice message delivery in ai_manager.py.
"""

import io
import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from common.tts_engine import (
    synthesize_cyberchad_voice,
    synthesize_cyberchad_voice_with_meta,
    clean_tts_text,
    get_preset,
    get_random_preset,
    list_presets,
    CYBERCHAD_PRESETS,
    CyberchadPreset,
    DEFAULT_VOICE,
    CYBERCHAD_FFMPEG_FILTER,
)


class TestCyberchadPresets:
    """Tests for preset management, registry, and configuration in common/tts_engine.py."""

    def test_preset_registry_inventory(self):
        """Validates that all expected presets are configured with valid parameters."""
        expected_keys = {
            "classic", "heavy_bass", "cyborg", "intercom",
            "fast_aggressive", "overdrive", "infernal",
            "drill_sergeant", "bunker", "studio_radio"
        }
        assert expected_keys == set(CYBERCHAD_PRESETS.keys())
        assert len(CYBERCHAD_PRESETS) == 10

        for key, p in CYBERCHAD_PRESETS.items():
            assert isinstance(p, CyberchadPreset)
            assert p.key == key
            assert len(p.name) > 0
            assert len(p.description) > 0
            assert p.voice == "ru-RU-DmitryNeural"
            assert p.rate.startswith(("+", "-")) and p.rate.endswith("%")
            assert p.pitch.startswith(("+", "-")) and p.pitch.endswith("Hz")
            assert len(p.ffmpeg_filter) > 0
            assert p.weight > 0
            assert "aresample=48000" in p.ffmpeg_filter
            assert p.caption_title == "🔥 Разъёб от Киберчеда"

    def test_list_presets(self):
        presets = list_presets()
        assert len(presets) == len(CYBERCHAD_PRESETS)
        assert all(isinstance(p, CyberchadPreset) for p in presets)

    def test_get_preset_by_key_and_name(self):
        # By key
        p_heavy = get_preset("heavy_bass")
        assert p_heavy.key == "heavy_bass"
        assert p_heavy.name == "Heavy Bass Boss"

        # By name (case insensitive)
        p_cyborg = get_preset("Cybernetic Borg")
        assert p_cyborg.key == "cyborg"

        p_infernal = get_preset("infernal titan")
        assert p_infernal.key == "infernal"

        # By preset instance
        assert get_preset(p_heavy) is p_heavy

    def test_get_preset_fallback(self):
        # Unknown key falls back gracefully
        fallback = get_preset("non_existent_preset_xyz")
        assert isinstance(fallback, CyberchadPreset)
        assert fallback.key in CYBERCHAD_PRESETS

    def test_get_random_preset(self):
        random_preset = get_random_preset()
        assert isinstance(random_preset, CyberchadPreset)
        assert random_preset.key in CYBERCHAD_PRESETS


class TestCyberchadTTSEngine:
    """Tests for synthesis, text cleaning, DSP modulation, and fallbacks."""

    @pytest.mark.asyncio
    async def test_synthesize_empty_or_none(self):
        assert await synthesize_cyberchad_voice("") is None
        assert await synthesize_cyberchad_voice("   ") is None
        assert await synthesize_cyberchad_voice(None) is None

        res_bytes, _ = await synthesize_cyberchad_voice_with_meta("")
        assert res_bytes is None

    def test_clean_tts_text(self):
        dirty = "<b>Слышь</b>, анон! 🔥💩 <i>Твой трек</i> — кал.<br>Удали. 🤖📻⚡"
        clean = clean_tts_text(dirty)
        assert "<b>" not in clean
        assert "🔥" not in clean
        assert "💩" not in clean
        assert "🤖" not in clean
        assert "Слышь, анон! Твой трек — кал. Удали." in clean

    def test_clean_tts_text_truncation(self):
        long_text = "а" * 1500
        clean = clean_tts_text(long_text)
        assert len(clean) == 1003  # 1000 + "..."
        assert clean.endswith("...")

    @pytest.mark.asyncio
    async def test_edge_tts_with_specific_preset(self):
        text = "Разъёб босса качалки."
        preset = CYBERCHAD_PRESETS["heavy_bass"]

        with patch("edge_tts.Communicate") as mock_comm_cls:
            mock_comm = AsyncMock()
            mock_comm.save = AsyncMock()
            mock_comm_cls.return_value = mock_comm

            with patch("shutil.which", return_value="C:\\ffmpeg\\bin\\ffmpeg.exe"):
                with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
                    mock_proc = AsyncMock()
                    mock_proc.communicate.return_value = (b"", b"")
                    mock_exec.return_value = mock_proc

                    with patch("os.path.exists", return_value=True):
                        with patch("os.path.getsize", return_value=5000):
                            with patch("builtins.open", MagicMock(return_value=io.BytesIO(b"MOCK_HEAVY_OGG"))):
                                res_bytes, used_preset = await synthesize_cyberchad_voice_with_meta(
                                    text, preset="heavy_bass"
                                )
                                assert res_bytes == b"MOCK_HEAVY_OGG"
                                assert used_preset.key == "heavy_bass"

                                # Verify edge_tts was called with heavy_bass voice, rate, pitch
                                mock_comm_cls.assert_called_once_with(
                                    text,
                                    preset.voice,
                                    rate=preset.rate,
                                    pitch=preset.pitch,
                                    connect_timeout=7,
                                    receive_timeout=20
                                )

                                # Verify FFmpeg was called with heavy_bass DSP filter
                                mock_exec.assert_called_once()
                                cmd_args = mock_exec.call_args[0]
                                assert preset.ffmpeg_filter in cmd_args

    @pytest.mark.asyncio
    async def test_edge_tts_success_with_ffmpeg_dsp(self):
        text = "Оценка: 0/10. Кал высшей пробы."

        with patch("edge_tts.Communicate") as mock_comm_cls:
            mock_comm = AsyncMock()
            mock_comm.save = AsyncMock()
            mock_comm_cls.return_value = mock_comm

            with patch("shutil.which", return_value="C:\\ffmpeg\\bin\\ffmpeg.exe"):
                with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
                    mock_proc = AsyncMock()
                    mock_proc.communicate.return_value = (b"", b"")
                    mock_exec.return_value = mock_proc

                    with patch("os.path.exists", return_value=True):
                        with patch("os.path.getsize", return_value=5000):
                            with patch("builtins.open", MagicMock(return_value=io.BytesIO(b"MOCK_OGG_BYTES"))):
                                result = await synthesize_cyberchad_voice(text, preset="classic", apply_dsp=True)
                                assert result == b"MOCK_OGG_BYTES"
                                mock_exec.assert_called_once()
                                cmd_args = mock_exec.call_args[0]
                                assert CYBERCHAD_PRESETS["classic"].ffmpeg_filter in cmd_args

    @pytest.mark.asyncio
    async def test_edge_tts_failure_falls_back_to_gtts(self):
        text = "Резервный синтез речи через Google."

        with patch("edge_tts.Communicate", side_effect=RuntimeError("Edge WebSocket Error")):
            with patch("gtts.gTTS") as mock_gtts_cls:
                mock_gtts = MagicMock()
                mock_gtts_cls.return_value = mock_gtts

                with patch("shutil.which", return_value="C:\\ffmpeg\\bin\\ffmpeg.exe"):
                    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
                        mock_proc = AsyncMock()
                        mock_proc.communicate.return_value = (b"", b"")
                        mock_exec.return_value = mock_proc

                        with patch("os.path.exists", return_value=True):
                            with patch("os.path.getsize", return_value=3000):
                                with patch("builtins.open", MagicMock(return_value=io.BytesIO(b"MOCK_GTTS_OGG"))):
                                    result = await synthesize_cyberchad_voice(text, preset="cyborg")
                                    assert result == b"MOCK_GTTS_OGG"
                                    mock_gtts_cls.assert_called_once()
                                    # DSP should still be executed on gTTS output
                                    mock_exec.assert_called_once()
                                    cmd_args = mock_exec.call_args[0]
                                    assert CYBERCHAD_PRESETS["cyborg"].ffmpeg_filter in cmd_args

    @pytest.mark.asyncio
    async def test_ffmpeg_missing_falls_back_to_raw_mp3(self):
        text = "Тест без установленного ffmpeg."

        with patch("edge_tts.Communicate") as mock_comm_cls:
            mock_comm = AsyncMock()
            mock_comm.save = AsyncMock()
            mock_comm_cls.return_value = mock_comm

            with patch("shutil.which", return_value=None):
                with patch("os.path.exists", return_value=True):
                    with patch("os.path.getsize", return_value=4000):
                        with patch("builtins.open", MagicMock(return_value=io.BytesIO(b"MOCK_RAW_MP3"))):
                            result = await synthesize_cyberchad_voice(text)
                            assert result == b"MOCK_RAW_MP3"


class TestVoiceRoastCyberchadIntegration:
    """Tests that voice notes and music roasts trigger Cyberchad voice replies with dynamic personas."""

    @pytest.mark.asyncio
    @patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock)
    @patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
    @patch("ai_manager.httpx.AsyncClient")
    async def test_voice_note_sends_cyberchad_voice_reply(self, mock_httpx_cls, mock_summarize, mock_synth_meta):
        from ai_manager import transcribe_and_roast_voice_note

        mock_bot = AsyncMock()
        mock_bot.get_file.return_value = MagicMock(file_path="voice/note.ogg", file_size=500_000)
        mock_bot.download_file.return_value = io.BytesIO(b"MOCK_OGG_VOICE")

        mock_http_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"text": "Привет всем в этом чатике"}
        mock_http_client.post.return_value = mock_resp
        mock_httpx_cls.return_value.__aenter__.return_value = mock_http_client

        mock_msg = MagicMock()
        mock_msg.content_type = 'voice'
        mock_msg.voice = MagicMock(duration=15, file_id="voice_123", file_size=500_000)
        mock_msg.video_note = None
        mock_msg.reply = AsyncMock()
        mock_msg.reply_voice = AsyncMock()

        mock_summarize.return_value = "Твой голос звучит омерзительно. 0/10 💩"
        preset = CYBERCHAD_PRESETS["heavy_bass"]
        mock_synth_meta.return_value = (b"MOCK_TTS_BYTES", preset)

        with patch("common.token_pool.groq_pool.get_all_active_tokens", return_value=["test-groq-key"]):
            await transcribe_and_roast_voice_note(mock_bot, mock_msg, board_id="b", stream="ru")

        # Verify text reply sent
        mock_msg.reply.assert_called_once()
        # Verify Cyberchad voice reply sent with unitary caption
        mock_synth_meta.assert_called_once()
        mock_msg.reply_voice.assert_called_once()
        _, kwargs = mock_msg.reply_voice.call_args
        assert kwargs.get("caption") == "🔥 Разъёб от Киберчеда"

    @pytest.mark.asyncio
    @patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock)
    @patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
    @patch("ai_manager.httpx.AsyncClient")
    async def test_music_roast_sends_cyberchad_voice_reply(self, mock_httpx_cls, mock_summarize, mock_synth_meta):
        from ai_manager import handle_music_roast

        mock_bot = AsyncMock()
        mock_bot.get_file.return_value = MagicMock(file_path="music/song.mp3", file_size=3_000_000)
        mock_bot.download_file.return_value = io.BytesIO(b"MOCK_AUDIO")

        mock_http_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"text": "Семпл трека"}
        mock_http_client.post.return_value = mock_resp
        mock_httpx_cls.return_value.__aenter__.return_value = mock_http_client

        mock_msg = MagicMock()
        mock_msg.audio = MagicMock(
            performer="OG Buda", title="Бандит",
            duration=90, file_size=3_000_000, file_id="buda_01",
            file_name="buda.mp3"
        )
        mock_msg.document = None
        mock_msg.reply = AsyncMock()
        mock_msg.reply_voice = AsyncMock()

        mock_summarize.return_value = "Бессвязный мамкин рэпчик. 1/10 💩 (Кал)"
        preset = CYBERCHAD_PRESETS["cyborg"]
        mock_synth_meta.return_value = (b"CYBERCHAD_MUSIC_VOICE", preset)

        await handle_music_roast(mock_bot, mock_msg, board_id="b", stream="ru")

        mock_msg.reply.assert_called_once()
        mock_synth_meta.assert_called_once()
        mock_msg.reply_voice.assert_called_once()
        _, kwargs = mock_msg.reply_voice.call_args
        assert kwargs.get("caption") == "🔥 Разъёб от Киберчеда"

    @pytest.mark.asyncio
    @patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock)
    @patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
    @patch("ai_manager.httpx.AsyncClient")
    async def test_voice_roast_falls_back_to_answer_voice_when_reply_fails(self, mock_httpx_cls, mock_summarize, mock_synth_meta):
        from ai_manager import transcribe_and_roast_voice_note
        from aiogram.exceptions import TelegramBadRequest

        mock_bot = AsyncMock()
        mock_bot.get_file.return_value = MagicMock(file_path="voice/note.ogg", file_size=500_000)
        mock_bot.download_file.return_value = io.BytesIO(b"MOCK_OGG_VOICE")

        mock_http_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"text": "Привет всем"}
        mock_http_client.post.return_value = mock_resp
        mock_httpx_cls.return_value.__aenter__.return_value = mock_http_client

        mock_msg = MagicMock()
        mock_msg.content_type = 'voice'
        mock_msg.voice = MagicMock(duration=10, file_id="voice_123", file_size=500_000)
        mock_msg.video_note = None
        mock_msg.reply = AsyncMock()
        mock_msg.reply_voice = AsyncMock(side_effect=TelegramBadRequest(method="sendVoice", message="message to be replied not found"))
        mock_msg.answer_voice = AsyncMock()

        mock_summarize.return_value = "Твой голос ужасен. 0/10 💩"
        preset = CYBERCHAD_PRESETS["classic"]
        mock_synth_meta.return_value = (b"CYBERCHAD_VOICE_BYTES", preset)

        await transcribe_and_roast_voice_note(mock_bot, mock_msg, board_id="b", stream="ru")

        mock_msg.reply_voice.assert_called_once()
        mock_msg.answer_voice.assert_called_once()
        assert mock_msg.answer_voice.call_args[1].get("caption") == "🔥 Разъёб от Киберчеда"

    @pytest.mark.asyncio
    @patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock)
    @patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
    @patch("ai_manager.httpx.AsyncClient")
    async def test_music_roast_falls_back_to_answer_voice_when_reply_fails(self, mock_httpx_cls, mock_summarize, mock_synth_meta):
        from ai_manager import handle_music_roast
        from aiogram.exceptions import TelegramBadRequest

        mock_bot = AsyncMock()
        mock_bot.get_file.return_value = MagicMock(file_path="music/track.mp3", file_size=1_000_000)
        mock_bot.download_file.return_value = io.BytesIO(b"MOCK_AUDIO")

        mock_http_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"text": "Трек"}
        mock_http_client.post.return_value = mock_resp
        mock_httpx_cls.return_value.__aenter__.return_value = mock_http_client

        mock_msg = MagicMock()
        mock_msg.audio = MagicMock(
            performer="Artist", title="Track",
            duration=60, file_size=1_000_000, file_id="tr_01",
            file_name="track.mp3"
        )
        mock_msg.document = None
        mock_msg.reply = AsyncMock()
        mock_msg.reply_voice = AsyncMock(side_effect=TelegramBadRequest(method="sendVoice", message="message to reply not found"))
        mock_msg.answer_voice = AsyncMock()

        mock_summarize.return_value = "Кал. 0/10 💩 (Кринж)"
        preset = CYBERCHAD_PRESETS["infernal"]
        mock_synth_meta.return_value = (b"CYBERCHAD_VOICE_BYTES", preset)

        await handle_music_roast(mock_bot, mock_msg, board_id="b", stream="ru")

        mock_msg.reply_voice.assert_called_once()
        mock_msg.answer_voice.assert_called_once()
        assert mock_msg.answer_voice.call_args[1].get("caption") == "🔥 Разъёб от Киберчеда"

    @pytest.mark.asyncio
    @patch("ai_manager.handle_music_roast", new_callable=AsyncMock)
    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_roast_album_tracks_sequentially(self, mock_sleep, mock_handle_music_roast):
        from delivery_manager import _roast_album_tracks_sequentially

        mock_bot = AsyncMock()
        msg1 = MagicMock()
        msg2 = MagicMock()
        audio_msgs = [msg1, msg2]

        await _roast_album_tracks_sequentially(mock_bot, audio_msgs, board_id="b", stream="ru", post_num=42)

        assert mock_handle_music_roast.call_count == 2
        mock_handle_music_roast.assert_any_call(mock_bot, msg1, "b", stream="ru", post_num=42)
        mock_handle_music_roast.assert_any_call(mock_bot, msg2, "b", stream="ru", post_num=42)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(2.0)


class TestSafeSendVoiceRoast:
    """Tests for _safe_send_voice_roast helper in ai_manager.py."""

    @pytest.mark.asyncio
    async def test_empty_message_or_bytes(self):
        from ai_manager import _safe_send_voice_roast
        assert await _safe_send_voice_roast(None, b"BYTES") is False
        mock_msg = MagicMock()
        assert await _safe_send_voice_roast(mock_msg, None) is False
        assert await _safe_send_voice_roast(mock_msg, b"") is False

    @pytest.mark.asyncio
    async def test_successful_reply_voice_passes_allow_sending_without_reply(self):
        from ai_manager import _safe_send_voice_roast
        mock_msg = MagicMock()
        mock_msg.reply_voice = AsyncMock()
        mock_msg.answer_voice = AsyncMock()

        result = await _safe_send_voice_roast(mock_msg, b"MOCK_VOICE", caption="🔥 Тест")
        assert result is True
        mock_msg.reply_voice.assert_called_once()
        _, kwargs = mock_msg.reply_voice.call_args
        assert kwargs.get("allow_sending_without_reply") is True
        assert kwargs.get("caption") == "🔥 Тест"
        mock_msg.answer_voice.assert_not_called()

    @pytest.mark.asyncio
    async def test_fallback_when_reply_fails_with_message_not_found(self):
        from ai_manager import _safe_send_voice_roast
        from aiogram.exceptions import TelegramBadRequest

        mock_msg = MagicMock()
        mock_msg.reply_voice = AsyncMock(side_effect=TelegramBadRequest(method="sendVoice", message="message to be replied not found"))
        mock_msg.answer_voice = AsyncMock()

        result = await _safe_send_voice_roast(mock_msg, b"MOCK_VOICE", caption="🔥 Тест")
        assert result is True
        mock_msg.reply_voice.assert_called_once()
        mock_msg.answer_voice.assert_called_once()
        _, kwargs = mock_msg.answer_voice.call_args
        assert kwargs.get("caption") == "🔥 Тест"

    @pytest.mark.asyncio
    async def test_voice_messages_forbidden_fails_gracefully(self):
        from ai_manager import _safe_send_voice_roast
        from aiogram.exceptions import TelegramBadRequest

        mock_msg = MagicMock()
        mock_msg.reply_voice = AsyncMock(side_effect=TelegramBadRequest(method="sendVoice", message="Bad Request: VOICE_MESSAGES_FORBIDDEN"))
        mock_msg.answer_voice = AsyncMock()

        result = await _safe_send_voice_roast(mock_msg, b"MOCK_VOICE", caption="🔥 Тест")
        assert result is False
        mock_msg.reply_voice.assert_called_once()
        mock_msg.answer_voice.assert_not_called()

    @pytest.mark.asyncio
    async def test_bot_blocked_forbidden_error_handled_gracefully(self):
        from ai_manager import _safe_send_voice_roast
        from aiogram.exceptions import TelegramForbiddenError

        mock_msg = MagicMock()
        mock_msg.reply_voice = AsyncMock(side_effect=TelegramForbiddenError(method="sendVoice", message="Forbidden: bot was blocked by the user"))
        mock_msg.answer_voice = AsyncMock()

        result = await _safe_send_voice_roast(mock_msg, b"MOCK_VOICE", caption="🔥 Тест")
        assert result is False
        mock_msg.reply_voice.assert_called_once()
        mock_msg.answer_voice.assert_not_called()


class TestCyberchadBoardBroadcast:
    """Tests that voice and music roasts are broadcast to the entire board via process_new_post."""

    @pytest.mark.asyncio
    @patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock)
    @patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
    @patch("ai_manager.httpx.AsyncClient")
    async def test_voice_note_broadcasts_voice_post_to_board(self, mock_httpx_cls, mock_summarize, mock_synth_meta):
        from ai_manager import transcribe_and_roast_voice_note

        mock_bot = AsyncMock()
        mock_bot.get_file.return_value = MagicMock(file_path="voice/note.ogg", file_size=500_000)
        mock_bot.download_file.return_value = io.BytesIO(b"MOCK_OGG_VOICE")

        mock_http_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"text": "Тестовое голосовое сообщение"}
        mock_http_client.post.return_value = mock_resp
        mock_httpx_cls.return_value.__aenter__.return_value = mock_http_client

        mock_msg = MagicMock()
        mock_msg.content_type = 'voice'
        mock_msg.voice = MagicMock(duration=10, file_id="v_101", file_size=500_000)
        mock_msg.video_note = None
        mock_msg.from_user = MagicMock(id=999, is_bot=False)
        mock_msg.reply = AsyncMock()
        mock_msg.reply_voice = AsyncMock()

        mock_summarize.return_value = "Твой войс ужасен. 0/10 💩"
        preset = CYBERCHAD_PRESETS["classic"]
        mock_synth_meta.return_value = (b"CYBERCHAD_VOICE_OGG", preset)

        with patch("common.bot_helpers.process_new_post", new_callable=AsyncMock) as mock_process_post:
            await transcribe_and_roast_voice_note(mock_bot, mock_msg, board_id="b", stream="ru", post_num=777)

            # process_new_post called twice: 1 for text, 1 for voice
            assert mock_process_post.call_count == 2
            
            # 1st call: text roast
            call_text_params = mock_process_post.call_args_list[0][0][0]
            assert call_text_params.board_id == "b"
            assert call_text_params.reply_to_post == 777
            assert call_text_params.content["type"] == "text"
            assert call_text_params.content["is_ai_roast"] is True

            # 2nd call: voice roast
            call_voice_params = mock_process_post.call_args_list[1][0][0]
            assert call_voice_params.board_id == "b"
            assert call_voice_params.reply_to_post == 777
            assert call_voice_params.content["type"] == "voice"
            assert call_voice_params.content["voice_bytes"] == b"CYBERCHAD_VOICE_OGG"
            assert call_voice_params.content["caption"] == "🔥 Разъёб от Киберчеда"
            assert call_voice_params.content["is_ai_roast"] is True
            assert call_voice_params.content["is_ai"] is True
            assert call_voice_params.content["reply_to"] == 777

    @pytest.mark.asyncio
    @patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock)
    @patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
    @patch("ai_manager.httpx.AsyncClient")
    async def test_music_roast_broadcasts_voice_post_to_board(self, mock_httpx_cls, mock_summarize, mock_synth_meta):
        from ai_manager import handle_music_roast

        mock_bot = AsyncMock()
        mock_bot.get_file.return_value = MagicMock(file_path="music/song.mp3", file_size=1_000_000)
        mock_bot.download_file.return_value = io.BytesIO(b"MOCK_AUDIO")

        mock_http_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"text": "Текст песни"}
        mock_http_client.post.return_value = mock_resp
        mock_httpx_cls.return_value.__aenter__.return_value = mock_http_client

        mock_msg = MagicMock()
        mock_msg.audio = MagicMock(
            performer="OG Buda", title="Бандит",
            duration=90, file_size=1_000_000, file_id="buda_01",
            file_name="buda.mp3"
        )
        mock_msg.document = None
        mock_msg.from_user = MagicMock(id=888, is_bot=False)
        mock_msg.reply = AsyncMock()
        mock_msg.reply_voice = AsyncMock()

        mock_summarize.return_value = "Мамкин рэпчик. 0/10 💩"
        preset = CYBERCHAD_PRESETS["cyborg"]
        mock_synth_meta.return_value = (b"CYBERCHAD_MUSIC_OGG", preset)

        with patch("common.bot_helpers.process_new_post", new_callable=AsyncMock) as mock_process_post:
            await handle_music_roast(mock_bot, mock_msg, board_id="b", stream="ru", post_num=888)

            assert mock_process_post.call_count == 2

            call_text_params = mock_process_post.call_args_list[0][0][0]
            assert call_text_params.content["type"] == "text"
            assert call_text_params.reply_to_post == 888

            call_voice_params = mock_process_post.call_args_list[1][0][0]
            assert call_voice_params.content["type"] == "voice"
            assert call_voice_params.content["voice_bytes"] == b"CYBERCHAD_MUSIC_OGG"
            assert call_voice_params.content["caption"] == "🔥 Разъёб от Киберчеда"
            assert call_voice_params.content["is_ai_roast"] is True
            assert call_voice_params.content["is_ai"] is True
            assert call_voice_params.content["reply_to"] == 888


