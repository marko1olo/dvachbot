import pytest
import json
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from site_tgach.vision import describe_image, prepare_image_for_analysis


@pytest.fixture(autouse=True)
def reset_vision_module_state():
    import site_tgach.vision as v
    v._GLOBAL_GEMINI_LAST_CALL = 0.0
    v._GLOBAL_GROQ_LAST_CALL = 0.0
    v._LAST_VISION_CALL_TIME.clear()
    yield
    v._GLOBAL_GEMINI_LAST_CALL = 0.0
    v._GLOBAL_GROQ_LAST_CALL = 0.0
    v._LAST_VISION_CALL_TIME.clear()


class TestVisionCascade:
    """Tests for site_tgach/vision.py models cascade and fallback resilience."""

    VALID_VISION_MODELS = {
        "gemini-3.1-flash-lite",
        "gemini-2.5-flash",
        "gemini-3.5-flash-lite",
        "qwen/qwen3.6-27b",
        "llama-3.2-11b-vision-preview",
    }

    def test_invalid_gemini_2_5_flash_lite_is_excluded(self):
        """gemini-2.5-flash-lite (which caused 404 in logs) must not be present in the cascade."""
        import site_tgach.vision as v
        import inspect
        src = inspect.getsource(v.describe_image)
        assert "gemini-2.5-flash-lite" not in src

    @pytest.mark.asyncio
    @patch("site_tgach.vision.prepare_image_for_analysis", return_value=(b"fake_jpeg_bytes", None))
    @patch("site_tgach.vision.AsyncOpenAI")
    @patch("site_tgach.vision.google_pool.get_all_active_tokens", return_value=["test-gemini-key"])
    @patch("site_tgach.vision.groq_pool.get_all_active_tokens", return_value=["test-groq-key"])
    async def test_vision_success_primary_gemini(self, mock_groq_pool, mock_google_pool, mock_openai_cls, mock_prep):
        mock_client = AsyncMock()
        mock_openai_cls.return_value = mock_client
        mock_completion = MagicMock()
        mock_choice = MagicMock()
        mock_choice.finish_reason = "stop"
        mock_choice.message.content = json.dumps({
            "tags": "1girl, solo, anime, blonde_hair",
            "description": "Тестовое описание изображения."
        })
        mock_completion.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_completion

        res = await describe_image("/dummy/path.jpg", source="TEST")
        assert res is not None
        parsed = json.loads(res)
        assert "tags" in parsed
        assert "1girl" in parsed["tags"]
        assert "blonde_hair" in parsed["tags"]

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] in self.VALID_VISION_MODELS
        assert call_kwargs["model"] == "gemini-3.1-flash-lite"

    @pytest.mark.asyncio
    @patch("site_tgach.vision.prepare_image_for_analysis", return_value=(b"fake_jpeg_bytes", None))
    @patch("site_tgach.vision.AsyncOpenAI")
    @patch("site_tgach.vision.google_pool.get_all_active_tokens", return_value=["test-gemini-key"])
    @patch("site_tgach.vision.groq_pool.get_all_active_tokens", return_value=["test-groq-key"])
    async def test_vision_gemini_404_falls_back_to_next_models(self, mock_groq_pool, mock_google_pool, mock_openai_cls, mock_prep):
        """When a model returns 404, it immediately falls back to the next model in cascade."""
        mock_client_404 = AsyncMock()
        mock_client_404.chat.completions.create.side_effect = Exception("404 Model Not Found")

        mock_client_ok = AsyncMock()
        mock_choice = MagicMock()
        mock_choice.finish_reason = "stop"
        mock_choice.message.content = json.dumps({
            "tags": "cat, animal, cute",
            "description": "Кот спит на диване."
        })
        mock_completion = MagicMock(choices=[mock_choice])
        mock_client_ok.chat.completions.create.return_value = mock_completion

        mock_openai_cls.side_effect = [mock_client_404, mock_client_ok]

        res = await describe_image("/dummy/path.jpg", source="TEST")
        parsed = json.loads(res)
        assert "cat" in parsed["tags"]
        assert mock_openai_cls.call_count >= 2

    @pytest.mark.asyncio
    @patch("site_tgach.vision.prepare_image_for_analysis", return_value=(b"fake_jpeg_bytes", None))
    @patch("site_tgach.vision.AsyncOpenAI")
    @patch("site_tgach.vision.google_pool.get_all_active_tokens", return_value=["test-gemini-key"])
    @patch("site_tgach.vision.groq_pool.get_all_active_tokens", return_value=["test-groq-key"])
    async def test_vision_tpd_skips_provider_models(self, mock_groq_pool, mock_google_pool, mock_openai_cls, mock_prep):
        """When Gemini hits TPD, remaining Gemini models are skipped and Groq vision is queried."""
        mock_client_tpd = AsyncMock()
        mock_client_tpd.chat.completions.create.side_effect = Exception("daily token limit (TPD) reached")

        mock_client_groq = AsyncMock()
        mock_choice = MagicMock()
        mock_choice.finish_reason = "stop"
        mock_choice.message.content = json.dumps({
            "tags": "landscape, mountains, sky",
            "description": "Горы на закате."
        })
        mock_completion = MagicMock(choices=[mock_choice])
        mock_client_groq.chat.completions.create.return_value = mock_completion

        mock_openai_cls.side_effect = [mock_client_tpd, mock_client_groq]

        res = await describe_image("/dummy/path.jpg", source="TEST")
        parsed = json.loads(res)
        assert "landscape" in parsed["tags"]

        # Verify Groq was called
        groq_call = mock_openai_cls.call_args_list[-1]
        assert "groq" in groq_call[1]["base_url"]

    @pytest.mark.asyncio
    @patch("site_tgach.vision.prepare_image_for_analysis", return_value=(b"fake_jpeg_bytes", None))
    @patch("site_tgach.vision.AsyncOpenAI")
    @patch("site_tgach.vision.google_pool.get_all_active_tokens", return_value=[])
    @patch("site_tgach.vision.groq_pool.get_all_active_tokens", return_value=[])
    async def test_vision_no_tokens_returns_error_exhausted(self, mock_groq_pool, mock_google_pool, mock_openai_cls, mock_prep):
        res = await describe_image("/dummy/path.jpg", source="TEST")
        assert res == "error_api_exhausted"
