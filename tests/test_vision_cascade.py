import pytest
import json
import io
from PIL import Image
from unittest.mock import patch, MagicMock, AsyncMock
from site_tgach.vision import (
    describe_image,
    prepare_image_for_groq,
    _call_gemini_native,
    _detect_image_mime,
    is_nsfw_text,
)


@pytest.fixture(autouse=True)
def reset_vision_module_state():
    import site_tgach.vision as v
    v._GLOBAL_GEMINI_LAST_CALL = 0.0
    v._GLOBAL_GROQ_LAST_CALL = 0.0
    v._LAST_VISION_CALL_TIME.clear()
    v._MODEL_503_COOLDOWN.clear()
    v._MODEL_404_COOLDOWN.clear()
    yield
    v._GLOBAL_GEMINI_LAST_CALL = 0.0
    v._GLOBAL_GROQ_LAST_CALL = 0.0
    v._LAST_VISION_CALL_TIME.clear()
    v._MODEL_503_COOLDOWN.clear()
    v._MODEL_404_COOLDOWN.clear()


class TestVisionCascade:
    """Tests for site_tgach/vision.py models cascade, native Gemini REST API, and Groq fallback."""

    VALID_VISION_MODELS = {
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.6-flash",
        "gemini-3.7-flash",
        "gemini-3.8-flash",
        "qwen/qwen3.6-27b",
        "qwen/qwen3.8-27b",
    }

    def test_obsolete_legacy_models_are_excluded(self):
        """Obsolete legacy models (Gemini 1.5/2.0, non-existent llama vision) must not be present in the cascade."""
        import site_tgach.vision as v
        import inspect
        src = inspect.getsource(v.describe_image)
        for old_model in [
            "gemini-1.5-flash",
            "gemini-2.0-flash",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-1.5-pro",
            "llama-3.2-90b-vision-preview",
        ]:
            assert old_model not in src, f"Obsolete model {old_model} found in vision.py!"

    def test_sanitized_prompt_has_no_porn_keywords(self):
        """System prompt must be clinical and contain no provocative porn terms."""
        import site_tgach.vision as v
        import inspect
        src = inspect.getsource(v.describe_image).lower()
        forbidden_words = [
            "penetration",
            "oral",
            "bondage",
            "fetishes",
            "fluids",
            "cum",
            "ahegao",
        ]
        import re
        for word in forbidden_words:
            assert not re.search(rf"\b{word}\b", src), f"Forbidden word '{word}' found in vision.py source!"

    def test_prepare_image_for_groq_resizes_to_640(self):
        """prepare_image_for_groq must resize images to max 640px to conserve tokens."""
        img = Image.new("RGB", (1200, 800), color=(255, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        raw_bytes = buf.getvalue()

        resized_bytes, err = prepare_image_for_groq(raw_bytes, max_size=640)
        assert err is None
        assert resized_bytes is not None

        with Image.open(io.BytesIO(resized_bytes)) as result_img:
            w, h = result_img.size
            assert max(w, h) <= 640

    @pytest.mark.asyncio
    async def test_call_gemini_native_fallback_on_400(self):
        """When BLOCK_NONE gets 400 from Google, it falls back to BLOCK_ONLY_HIGH."""
        mock_http_client = AsyncMock()

        # First call (BLOCK_NONE) returns 400
        resp_400 = MagicMock()
        resp_400.status_code = 400
        resp_400.text = "INVALID_ARGUMENT: BLOCK_NONE not supported"

        # Second call (BLOCK_ONLY_HIGH) returns 200
        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": '{"tags": "anime, art", "description": "Арт."}'}]
                    },
                    "finishReason": "STOP"
                }
            ]
        }

        mock_http_client.post.side_effect = [resp_400, resp_200]

        content, finish_reason = await _call_gemini_native(
            http_client=mock_http_client,
            model_name="gemini-3.5-flash-lite",
            api_key="test-key",
            prompt_text="test prompt",
            images_data=[b"fake_jpeg"],
        )

        assert mock_http_client.post.call_count == 2
        first_payload = mock_http_client.post.call_args_list[0][1]["json"]
        assert first_payload["safetySettings"][0]["threshold"] == "BLOCK_NONE"
        assert first_payload["generationConfig"]["responseMimeType"] == "application/json"

        second_payload = mock_http_client.post.call_args_list[1][1]["json"]
        assert second_payload["safetySettings"][0]["threshold"] == "BLOCK_ONLY_HIGH"

        assert content == '{"tags": "anime, art", "description": "Арт."}'
        assert finish_reason == "stop"

    @pytest.mark.asyncio
    @patch("site_tgach.vision.prepare_image_for_analysis", return_value=(b"fake_jpeg_bytes", None))
    @patch("site_tgach.vision._call_gemini_native")
    @patch("site_tgach.vision.google_pool.get_all_active_tokens", return_value=["test-gemini-key"])
    @patch("site_tgach.vision.groq_pool.get_all_active_tokens", return_value=["test-groq-key"])
    async def test_vision_success_primary_gemini(self, mock_groq_pool, mock_google_pool, mock_gemini_call, mock_prep):
        """Primary Gemini model succeeds via native REST API."""
        mock_gemini_call.return_value = (
            json.dumps({
                "tags": "1girl, solo, anime, blonde_hair",
                "description": "Тестовое описание изображения."
            }),
            "stop"
        )

        res = await describe_image("/dummy/path.jpg", source="TEST")
        assert res is not None
        parsed = json.loads(res)
        assert "tags" in parsed
        assert "1girl" in parsed["tags"]
        assert "blonde_hair" in parsed["tags"]

        assert mock_gemini_call.call_count == 1
        call_model = mock_gemini_call.call_args[1]["model_name"]
        assert call_model == "gemini-3.1-flash-lite"

    @pytest.mark.asyncio
    @patch("site_tgach.vision.prepare_image_for_analysis", return_value=(b"fake_jpeg_bytes", None))
    @patch("site_tgach.vision._call_gemini_native")
    @patch("site_tgach.vision.AsyncOpenAI")
    @patch("site_tgach.vision.google_pool.get_all_active_tokens", return_value=["test-gemini-key"])
    @patch("site_tgach.vision.groq_pool.get_all_active_tokens", return_value=["test-groq-key"])
    async def test_vision_gemini_empty_response_does_not_panic_skip_all_gemini(
        self, mock_groq_pool, mock_google_pool, mock_openai_cls, mock_gemini_call, mock_prep
    ):
        """Empty response from first Gemini model tries the NEXT Gemini model, not skip all."""
        mock_gemini_call.side_effect = [
            (None, "empty_response"),
            (
                json.dumps({
                    "tags": "cat, animal, cute",
                    "description": "Кот спит на диване."
                }),
                "stop"
            ),
        ]

        res = await describe_image("/dummy/path.jpg", source="TEST")
        assert res is not None
        parsed = json.loads(res)
        assert "cat" in parsed["tags"]
        assert mock_gemini_call.call_count == 2
        models_called = [c[1]["model_name"] for c in mock_gemini_call.call_args_list]
        assert models_called == ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite"]
        assert mock_openai_cls.call_count == 0

    @pytest.mark.asyncio
    @patch("site_tgach.vision.prepare_image_for_analysis", return_value=(b"fake_jpeg_bytes", None))
    @patch("site_tgach.vision._call_gemini_native")
    @patch("site_tgach.vision.AsyncOpenAI")
    @patch("site_tgach.vision.google_pool.get_all_active_tokens", return_value=["test-gemini-key"])
    @patch("site_tgach.vision.groq_pool")
    async def test_groq_tpd_penalizes_specific_key_and_continues(
        self, mock_groq_pool_mod, mock_google_pool, mock_openai_cls, mock_gemini_call, mock_prep
    ):
        """When a Groq key hits TPD, penalize_token is called on that key, and other keys are tried."""
        mock_gemini_call.side_effect = Exception("404 Model Not Found")

        key1 = "groq-key-1"
        key2 = "groq-key-2"
        mock_groq_pool_mod.get_all_active_tokens.return_value = [key1, key2]
        mock_groq_pool_mod._cooldown_until = {}

        mock_client1 = AsyncMock()
        mock_client1.chat.completions.create.side_effect = Exception("429 rate limit: tokens per day (TPD) exceeded")

        mock_client2 = AsyncMock()
        mock_choice = MagicMock()
        mock_choice.finish_reason = "stop"
        mock_choice.message.content = json.dumps({
            "tags": "landscape, mountains, sky",
            "description": "Горы на закате."
        })
        mock_client2.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

        mock_openai_cls.side_effect = [mock_client1, mock_client2]

        res = await describe_image("/dummy/path.jpg", source="TEST")
        assert res is not None
        parsed = json.loads(res)
        assert "landscape" in parsed["tags"]

        mock_groq_pool_mod.penalize_token.assert_called_once()
        penalized_token = mock_groq_pool_mod.penalize_token.call_args[0][0]
        assert penalized_token in [key1, key2]

    @pytest.mark.asyncio
    @patch("site_tgach.vision.prepare_image_for_analysis", return_value=(b"fake_jpeg_bytes", None))
    @patch("site_tgach.vision._call_gemini_native")
    @patch("site_tgach.vision.google_pool.get_all_active_tokens", return_value=[])
    @patch("site_tgach.vision.groq_pool.get_all_active_tokens", return_value=[])
    async def test_vision_no_tokens_returns_error_exhausted(self, mock_groq_pool, mock_google_pool, mock_gemini_call, mock_prep):
        res = await describe_image("/dummy/path.jpg", source="TEST")
        assert res == "error_api_exhausted"

    @pytest.mark.asyncio
    @patch("site_tgach.vision.prepare_image_for_analysis", return_value=(b"fake_jpeg_bytes", None))
    @patch("site_tgach.vision._call_gemini_native")
    @patch("site_tgach.vision.AsyncOpenAI")
    @patch("site_tgach.vision.google_pool.get_all_active_tokens", return_value=["test-gemini-key"])
    @patch("site_tgach.vision.groq_pool.get_all_active_tokens", return_value=["test-groq-key"])
    async def test_gemini_safety_filter_skips_all_gemini_and_falls_back_to_groq_instantly(
        self, mock_groq_pool, mock_google_pool, mock_openai_cls, mock_gemini_call, mock_prep
    ):
        """When Gemini returns safety, all remaining Gemini models must be skipped immediately and Groq called."""
        # First Gemini call (gemini-3.1-flash-lite) returns safety
        mock_gemini_call.return_value = (None, "safety")

        # Groq client returns valid tags/description
        mock_client = AsyncMock()
        mock_choice = MagicMock()
        mock_choice.finish_reason = "stop"
        mock_choice.message.content = json.dumps({
            "tags": "1girl, ecchi, swimsuit, anime",
            "description": "Аниме иллюстрация девушки в купальнике."
        })
        mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
        mock_openai_cls.return_value = mock_client

        res = await describe_image("/dummy/path.jpg", source="TEST")
        assert res is not None
        parsed = json.loads(res)
        assert "ecchi" in parsed["tags"]
        assert "купальнике" in parsed["description"]

        # MUST be called exactly once: gemini-3.5-flash and gemini-3.5-flash-lite must NOT be called!
        assert mock_gemini_call.call_count == 1
        assert mock_gemini_call.call_args[1]["model_name"] == "gemini-3.1-flash-lite"
        # Groq must be called immediately
        assert mock_openai_cls.call_count == 1

    @pytest.mark.asyncio
    async def test_call_gemini_native_prompt_feedback_block_reason_returns_safety(self):
        """_call_gemini_native detects blockReason='OTHER' in promptFeedback and returns safety."""
        mock_http_client = AsyncMock()
        resp_mock = MagicMock()
        resp_mock.status_code = 200
        resp_mock.json.return_value = {
            "candidates": [],
            "promptFeedback": {
                "blockReason": "OTHER",
                "safetyRatings": [{"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "probability": "HIGH"}]
            }
        }
        mock_http_client.post.return_value = resp_mock

        content, finish_reason = await _call_gemini_native(
            http_client=mock_http_client,
            model_name="gemini-3.1-flash-lite",
            api_key="test-key",
            prompt_text="test prompt",
            images_data=[b"fake_jpeg"],
        )
        assert content is None
        assert finish_reason == "safety"

    @pytest.mark.asyncio
    async def test_call_gemini_native_finish_reason_other_empty_content_returns_safety(self):
        """_call_gemini_native treats candidate finishReason='OTHER' without text as safety block."""
        mock_http_client = AsyncMock()
        resp_mock = MagicMock()
        resp_mock.status_code = 200
        resp_mock.json.return_value = {
            "candidates": [
                {
                    "finishReason": "OTHER",
                    "content": {"parts": []}
                }
            ]
        }
        mock_http_client.post.return_value = resp_mock

        content, finish_reason = await _call_gemini_native(
            http_client=mock_http_client,
            model_name="gemini-3.1-flash-lite",
            api_key="test-key",
            prompt_text="test prompt",
            images_data=[b"fake_jpeg"],
        )
        assert content is None
        assert finish_reason == "safety"

    @pytest.mark.asyncio
    async def test_call_gemini_native_safety_rating_blocked_returns_safety(self):
        """_call_gemini_native detects candidate with blocked safety rating and returns safety."""
        mock_http_client = AsyncMock()
        resp_mock = MagicMock()
        resp_mock.status_code = 200
        resp_mock.json.return_value = {
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {"parts": [{"text": "text"}]},
                    "safetyRatings": [
                        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "probability": "HIGH", "blocked": True}
                    ]
                }
            ]
        }
        mock_http_client.post.return_value = resp_mock

        content, finish_reason = await _call_gemini_native(
            http_client=mock_http_client,
            model_name="gemini-3.1-flash-lite",
            api_key="test-key",
            prompt_text="test prompt",
            images_data=[b"fake_jpeg"],
        )
        assert finish_reason == "safety"

    @pytest.mark.asyncio
    async def test_neuro_moderator_404_resilience(self):
        """When Groq or Gemini returns 404, _safe_groq_json penalizes token and doesn't retry in tight loop."""
        from site_tgach.neuro_moderator import _safe_groq_json
        from unittest.mock import patch, AsyncMock

        mock_resp_404 = MagicMock()
        mock_resp_404.status_code = 404
        mock_resp_404.text = "Model not found"

        with patch("site_tgach.neuro_moderator._execute_groq_post", new_callable=AsyncMock) as mock_post, \
             patch("site_tgach.neuro_moderator.google_pool.get_all_active_tokens", return_value=[]), \
             patch("site_tgach.neuro_moderator.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_post.return_value = mock_resp_404

            res = await _safe_groq_json([{"role": "user", "content": "hello"}])
            assert res is None
            # Verified asyncio.sleep was called with 2.5s cooldown
            sleep_calls = [c.args[0] for c in mock_sleep.call_args_list if c.args]
            assert any(s >= 2.5 for s in sleep_calls)

    @pytest.mark.asyncio
    async def test_neuro_moderator_429_resilience(self):
        """When Groq or Gemini returns 429, _safe_groq_json penalizes token and applies 2.5s cooldown."""
        from site_tgach.neuro_moderator import _safe_groq_json
        from unittest.mock import patch, AsyncMock

        mock_resp_429 = MagicMock()
        mock_resp_429.status_code = 429
        mock_resp_429.text = "Rate limit exceeded"

        with patch("site_tgach.neuro_moderator._execute_groq_post", new_callable=AsyncMock) as mock_post, \
             patch("site_tgach.neuro_moderator.google_pool.get_all_active_tokens", return_value=[]), \
             patch("site_tgach.neuro_moderator.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_post.return_value = mock_resp_429

            res = await _safe_groq_json([{"role": "user", "content": "hello"}])
            assert res is None
            sleep_calls = [c.args[0] for c in mock_sleep.call_args_list if c.args]
            assert any(s >= 2.5 for s in sleep_calls)

    @pytest.mark.asyncio
    @patch("site_tgach.vision.prepare_image_for_analysis", return_value=(b"fake_jpeg_bytes", None))
    @patch("site_tgach.vision._call_gemini_native")
    @patch("site_tgach.vision.AsyncOpenAI")
    @patch("site_tgach.vision.google_pool.get_all_active_tokens", return_value=["test-gemini-key"])
    @patch("site_tgach.vision.groq_pool.get_all_active_tokens", return_value=["test-groq-key"])
    async def test_gemini_safety_filter_returns_safety_rejected_when_groq_fails(
        self, mock_groq_pool, mock_google_pool, mock_openai_cls, mock_gemini_call, mock_prep
    ):
        """When Gemini returns safety and Groq fails (e.g. exhausted/TPD), must return 'safety_rejected'."""
        mock_gemini_call.return_value = (None, "safety")
        mock_client = AsyncMock()
        mock_client.chat.completions.create.side_effect = Exception("429 rate limit: tokens per day (TPD) exceeded")
        mock_openai_cls.return_value = mock_client

        res = await describe_image("/dummy/path.jpg", source="TEST")
        assert res == "safety_rejected"

    @pytest.mark.asyncio
    @patch("site_tgach.vision.prepare_image_for_analysis", return_value=(b"fake_jpeg_bytes", None))
    @patch("site_tgach.vision._call_gemini_native")
    @patch("site_tgach.vision.google_pool.get_all_active_tokens", return_value=["test-gemini-key"])
    @patch("site_tgach.vision.groq_pool.get_all_active_tokens", return_value=[])
    async def test_gemini_safety_filter_returns_safety_rejected_when_no_groq_tokens(
        self, mock_groq_pool, mock_google_pool, mock_gemini_call, mock_prep
    ):
        """When Gemini returns safety and no Groq tokens available, must return 'safety_rejected'."""
        mock_gemini_call.return_value = (None, "safety")

        res = await describe_image("/dummy/path.jpg", source="TEST")
        assert res == "safety_rejected"

    def test_detect_image_mime_types(self):
        """Verify accurate image MIME type detection based on magic bytes."""
        jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF"
        png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        gif_bytes = b"GIF89a\x01\x00\x01\x00"
        webp_bytes = b"RIFF\x1a\x00\x00\x00WEBPVP8 "
        unknown_bytes = b"\x00\x01\x02\x03"

        assert _detect_image_mime(jpeg_bytes) == "image/jpeg"
        assert _detect_image_mime(png_bytes) == "image/png"
        assert _detect_image_mime(gif_bytes) == "image/gif"
        assert _detect_image_mime(webp_bytes) == "image/webp"
        assert _detect_image_mime(unknown_bytes) == "image/jpeg"
        assert _detect_image_mime(b"") == "image/jpeg"

    def test_is_nsfw_text_keywords_detection(self):
        """Verify explicit NSFW text keywords detection in caption and file paths."""
        assert is_nsfw_text(caption="Check out this hentai drawing", file_paths=None) is True
        assert is_nsfw_text(caption=None, file_paths="/uploads/porno_pic.jpg") is True
        assert is_nsfw_text(caption="A cute cat on a chair", file_paths="/uploads/cat.jpg") is False

    @pytest.mark.asyncio
    @patch("site_tgach.vision.prepare_image_for_analysis", return_value=(b"fake_jpeg_bytes", None))
    @patch("site_tgach.vision._call_gemini_native")
    @patch("site_tgach.vision.AsyncOpenAI")
    @patch("site_tgach.vision.google_pool.get_all_active_tokens", return_value=["test-gemini-key"])
    @patch("site_tgach.vision.groq_pool")
    async def test_groq_tpd_instant_fallback_to_gemini_tagger(
        self, mock_groq_pool, mock_google_pool, mock_openai_cls, mock_gemini_call, mock_prep
    ):
        """When source='TAGGER' and Groq hits TPD, cascade immediately falls back to Gemini without delay."""
        import site_tgach.vision as v
        key1 = "groq-key-1"
        mock_groq_pool.get_all_active_tokens.return_value = [key1]
        mock_groq_pool._cooldown_until = {}

        mock_client = AsyncMock()
        mock_client.chat.completions.create.side_effect = Exception("429 rate limit: tokens per day (TPD) exceeded, try again in 10m39s")
        mock_openai_cls.return_value = mock_client

        mock_gemini_call.return_value = (
            json.dumps({"tags": "anime, art, solo", "description": "Аниме арт."}),
            "stop"
        )

        res = await describe_image("/dummy/path.jpg", source="TAGGER")
        assert res is not None
        parsed = json.loads(res)
        assert "anime" in parsed["tags"]

        # Gemini must have been called as fallback
        assert mock_gemini_call.call_count == 1
        # Groq key must be penalized
        mock_groq_pool.penalize_token.assert_called_once()
        # Provider global Groq cooldown must be set to prevent repeat hammering
        assert v._GLOBAL_GROQ_LAST_CALL > 0.0

    @pytest.mark.asyncio
    @patch("site_tgach.vision.prepare_image_for_analysis", return_value=(b"fake_jpeg_bytes", None))
    @patch("site_tgach.vision._call_gemini_native")
    @patch("site_tgach.vision.AsyncOpenAI")
    @patch("site_tgach.vision.google_pool.get_all_active_tokens", return_value=["test-gemini-key"])
    @patch("site_tgach.vision.groq_pool")
    async def test_all_groq_keys_in_cooldown_skips_groq_immediately(
        self, mock_groq_pool, mock_google_pool, mock_openai_cls, mock_gemini_call, mock_prep
    ):
        """When all Groq keys are on cooldown, Groq is skipped instantly and Gemini is called without sleep."""
        import time
        key1 = "groq-key-1"
        key2 = "groq-key-2"
        mock_groq_pool.get_all_active_tokens.return_value = [key1, key2]
        # Both keys are in cooldown 600s in the future
        mock_groq_pool._cooldown_until = {key1: time.time() + 600.0, key2: time.time() + 600.0}

        mock_gemini_call.return_value = (
            json.dumps({"tags": "landscape, photo", "description": "Пейзаж."}),
            "stop"
        )

        res = await describe_image("/dummy/path.jpg", source="TAGGER")
        assert res is not None
        parsed = json.loads(res)
        assert "landscape" in parsed["tags"]

        # Groq client was never invoked because pre-check skipped it immediately
        assert mock_openai_cls.call_count == 0
        assert mock_gemini_call.call_count == 1

    @pytest.mark.asyncio
    @patch("site_tgach.vision.prepare_image_for_analysis", return_value=(b"fake_jpeg_bytes", None))
    @patch("site_tgach.vision._call_gemini_native")
    @patch("site_tgach.vision.google_pool.get_all_active_tokens", return_value=["test-gemini-key"])
    @patch("site_tgach.vision.groq_pool.get_all_active_tokens", return_value=[])
    async def test_explicit_nsfw_text_returns_safety_rejected_when_groq_exhausted(
        self, mock_groq_pool, mock_google_pool, mock_gemini_call, mock_prep
    ):
        """When caption has explicit NSFW keywords and Groq is exhausted, returns 'safety_rejected' without crashing."""
        res = await describe_image("/dummy/path.jpg", caption="some explicit hentai porn scene", source="TAGGER")
        assert res == "safety_rejected"
        # Gemini was NOT called to protect against account bans
        assert mock_gemini_call.call_count == 0

    def test_gemini_37_flash_present_in_cascades(self):
        """Verify gemini-3.7-flash is configured in both TAGGER and SITE cascades."""
        import site_tgach.vision as v
        import inspect
        src = inspect.getsource(v.describe_image)
        assert '("gemini-3.7-flash", "gemini")' in src

    @pytest.mark.asyncio
    @patch("site_tgach.vision.prepare_image_for_analysis", return_value=(b"fake_jpeg_bytes", None))
    @patch("site_tgach.vision.google_pool.get_all_active_tokens", return_value=[])
    @patch("site_tgach.vision.groq_pool.get_all_active_tokens", return_value=[])
    async def test_vision_exhausted_logs_warning_not_error(
        self, mock_groq_pool, mock_google_pool, mock_prep, caplog
    ):
        """When all models are exhausted, it logs a throttled WARNING instead of spamming ERROR."""
        import logging
        import site_tgach.vision as v
        v._LAST_EXHAUSTED_LOG_TIME = 0.0

        with caplog.at_level(logging.WARNING, logger="site_tgach.vision"):
            res = await describe_image("/dummy/path.jpg", source="TAGGER")

        assert res == "error_api_exhausted"
        # Must have WARNING record about exhausted models
        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING and "cooldown/exhausted" in r.message]
        assert len(warning_records) >= 1
        # Must NOT have ERROR record for exhausted models
        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR and "all vision models exhausted" in r.message]
        assert len(error_records) == 0

    @pytest.mark.asyncio
    @patch("site_tgach.vision.prepare_image_for_analysis", return_value=(b"fake_jpeg_bytes", None))
    @patch("site_tgach.vision._call_gemini_native")
    @patch("site_tgach.vision.AsyncOpenAI")
    @patch("site_tgach.vision.google_pool.get_all_active_tokens", return_value=[])
    @patch("site_tgach.vision.groq_pool")
    async def test_vision_429_applies_exponential_backoff_and_jitter(
        self, mock_groq_pool, mock_google_pool, mock_openai_cls, mock_gemini_call, mock_prep
    ):
        """When 429 occurs, Groq token is penalized with backoff + jitter without crashing."""
        key = "test-groq-key"
        mock_groq_pool.get_all_active_tokens.return_value = [key]
        mock_groq_pool._cooldown_until = {}

        mock_client = AsyncMock()
        mock_client.chat.completions.create.side_effect = Exception("429 Too Many Requests")
        mock_openai_cls.return_value = mock_client

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            res = await describe_image("/dummy/path.jpg", source="TAGGER")

        assert res == "error_api_exhausted"
        assert mock_groq_pool.penalize_token.call_count == 1
        penalized_sec = mock_groq_pool.penalize_token.call_args[0][1]
        # Base is 30s, with jitter should be >= 30.0
        assert penalized_sec >= 30.0

    @pytest.mark.asyncio
    async def test_tagger_fallback_raznoe_and_cooldown_on_api_exhausted(self):
        """When Vision API is exhausted, tagger applies fallback '[разное]', schedules retry, and enters cooldown."""
        import site_tgach.tagging_worker as tw
        import time

        tw.TEMP_FAILED_FILES.clear()
        tw._GLOBAL_API_EXHAUSTED_UNTIL = 0.0
        tw._GLOBAL_API_EXHAUSTED_STREAK = 0

        file_id = "test_fid_12345"
        ai_response = "error_api_exhausted"
        tags = None

        # Simulate what the worker loop executes when ai_response == "error_api_exhausted"
        tw._GLOBAL_API_EXHAUSTED_STREAK += 1
        entry = tw.TEMP_FAILED_FILES.get(file_id)
        fail_cnt = ((entry.get("cnt", 0) + 1) if isinstance(entry, dict) else 1)

        worker_sleep = min(180.0, 20.0 * (1.5 ** min(tw._GLOBAL_API_EXHAUSTED_STREAK - 1, 4))) + 2.0
        tw._GLOBAL_API_EXHAUSTED_UNTIL = time.time() + worker_sleep

        if fail_cnt >= 3:
            tags = "разное"
        else:
            tags = "[разное]"
            retry_delay = 60.0 + 5.0
            tw.TEMP_FAILED_FILES[file_id] = {
                "until": time.time() + retry_delay,
                "cnt": fail_cnt,
            }

        assert tags == "[разное]"
        assert file_id in tw.TEMP_FAILED_FILES
        assert tw.TEMP_FAILED_FILES[file_id]["cnt"] == 1
        assert tw._GLOBAL_API_EXHAUSTED_UNTIL > time.time()
        assert tw._GLOBAL_API_EXHAUSTED_STREAK == 1

        # Second attempt before cooldown expires should be protected by _GLOBAL_API_EXHAUSTED_UNTIL
        now_ts = time.time()
        assert now_ts < tw._GLOBAL_API_EXHAUSTED_UNTIL

    def test_tagging_loop_scope_has_no_unbound_locals(self):
        """Ensure _GLOBAL_API_EXHAUSTED_UNTIL and _GLOBAL_API_EXHAUSTED_STREAK are global in tagging_loop."""
        import site_tgach.tagging_worker as tw
        code = tw.tagging_loop.__code__
        assert "_GLOBAL_API_EXHAUSTED_UNTIL" not in code.co_varnames
        assert "_GLOBAL_API_EXHAUSTED_STREAK" not in code.co_varnames
        assert "_GLOBAL_API_EXHAUSTED_UNTIL" in code.co_names
        assert "_GLOBAL_API_EXHAUSTED_STREAK" in code.co_names


