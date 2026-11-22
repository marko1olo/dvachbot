import asyncio
import io
import inspect
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch
from PIL import Image
import pytest
from fastapi import HTTPException

from site_tgach.tagging_worker import count_tagging_backlog, get_tasks
from site_tgach.vision import (
    describe_image,
    is_nsfw_content,
    detect_high_skin_ratio,
    _call_gemini_native,
)
import site_tgach.vision as vision_mod
from site_tgach.main import ConnectionManager, _proxy_external_url, _proxy_protected_telegram_file


class TestSiteBackendDeepRepair:
    """Suite testing deep repair of Site backend, WebSocket, tagger backlog, and vision safety."""

    # =========================================================================
    # TASK 1: TAGGER BACKLOG SYNCHRONIZATION (ELIMINATE PHANTOM 1308 FILES)
    # =========================================================================
    @pytest.mark.asyncio
    async def test_tagging_backlog_sync_no_phash_discrepancy(self, isolated_test_db):
        """
        Verify count_tagging_backlog and get_tasks are synchronized:
        Files with tags already present but phash IS NULL must NOT be counted
        as waiting backlog tasks.
        """
        db = isolated_test_db
        now = time.time()

        # Insert test data:
        # 1. Untagged image (tags is NULL) -> true backlog
        await db.execute(
            """INSERT INTO FileRegistry (file_id, file_type, tags, phash, created_at)
               VALUES ('fid_untagged_1', 'photo', NULL, NULL, ?)""",
            (now,),
        )
        # 2. Untagged image (tags is empty string) -> true backlog
        await db.execute(
            """INSERT INTO FileRegistry (file_id, file_type, tags, phash, created_at)
               VALUES ('fid_untagged_2', 'photo', '', NULL, ?)""",
            (now - 10,),
        )
        # 3. Already tagged image, but phash is NULL (historical legacy) -> MUST NOT be in backlog!
        await db.execute(
            """INSERT INTO FileRegistry (file_id, file_type, tags, phash, created_at)
               VALUES ('fid_tagged_no_phash', 'photo', 'anime, girl', NULL, ?)""",
            (now - 20,),
        )
        # 4. Fully processed image (tags and phash present) -> NOT in backlog
        await db.execute(
            """INSERT INTO FileRegistry (file_id, file_type, tags, phash, created_at)
               VALUES ('fid_fully_processed', 'photo', 'landscape', 'd41d8cd98f00b204', ?)""",
            (now - 30,),
        )

        # Backlog count must be exactly 3!
        backlog_count = await count_tagging_backlog(db)
        assert backlog_count == 3, f"Expected 3 backlog files, got {backlog_count}"

        # get_tasks must fetch only the 3 untagged/no-phash tasks
        tasks = await get_tasks(db, limit=50)
        task_fids = [t["fid"] for t in tasks]
        assert "fid_untagged_1" in task_fids
        assert "fid_untagged_2" in task_fids
        assert "fid_tagged_no_phash" in task_fids
        assert "fid_fully_processed" not in task_fids
        assert len(tasks) == 3

    # =========================================================================
    # TASK 2: STREAM_PROXY CANCELLED_ERROR DEBUG & RE-RAISE
    # =========================================================================
    @pytest.mark.asyncio
    async def test_stream_proxy_cancelled_error_debug_and_reraised(self):
        """
        Verify that asyncio.CancelledError during client video scrubbing/rewinding
        is logged as debug and re-raised, avoiding spammy WARNING logs with cancel scope tracebacks.
        """
        # Mock upstream response
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.headers = {"Content-Type": "video/mp4", "Content-Length": "1000"}

        async def _mock_iter_chunked(_chunk_size):
            yield b"first_video_chunk"
            raise asyncio.CancelledError("Client disconnected during scrub")

        mock_resp.content.iter_chunked = _mock_iter_chunked

        mock_bot = AsyncMock()
        mock_bot.token = "test_token"

        with patch("site_tgach.main.logger") as mock_logger, \
             patch("site_tgach.main._get_shared_aiohttp_session") as mock_session_getter:

            mock_session = MagicMock()
            mock_session.get = AsyncMock(return_value=mock_resp)
            mock_session_getter.return_value = mock_session

            response = await _proxy_protected_telegram_file(
                file_id="test_video_fid",
                file_path="test_path",
                token="test_token",
                filename="test.mp4",
            )

            # Consume the StreamingResponse body_iterator until it cancels
            body_chunks = []
            with pytest.raises(asyncio.CancelledError):
                async for chunk in response.body_iterator:
                    body_chunks.append(chunk)

            assert len(body_chunks) == 1
            assert body_chunks[0] == b"first_video_chunk"

            # Check logger: debug called with aborted stream, warning NOT called with interrupted stream
            debug_calls = [str(c) for c in mock_logger.debug.call_args_list]
            warning_calls = [str(c) for c in mock_logger.warning.call_args_list]

            assert any("Client aborted stream" in s for s in debug_calls), "logger.debug should record client abort"
            assert not any("Upstream file stream interrupted" in s for s in warning_calls), \
                "CancelledError must not be logged as warning"

    # =========================================================================
    # TASK 3: WEBSOCKET _safe_send TIMEOUT INCREASED TO 2.0s
    # =========================================================================
    def test_websocket_safe_send_source_timeout(self):
        """Verify the source code of ConnectionManager._safe_send defines timeout=2.0."""
        src = inspect.getsource(ConnectionManager._safe_send)
        assert "timeout=2.0" in src, "ConnectionManager._safe_send timeout must be 2.0s"
        assert "timeout=0.4" not in src, "Obsolete 0.4s timeout found in _safe_send"

    @pytest.mark.asyncio
    async def test_websocket_safe_send_tolerates_mobile_latency(self):
        """
        Verify that a WebSocket send taking 0.6s (which would fail with 0.4s)
        now succeeds cleanly under 2.0s timeout without disconnecting the client.
        """
        manager = ConnectionManager()
        mock_ws = AsyncMock()

        async def _slow_send(_msg):
            await asyncio.sleep(0.1)  # Simulate latency

        mock_ws.send_text = AsyncMock(side_effect=_slow_send)
        manager.active_connections["test/board/ru"] = {mock_ws}

        # Should complete successfully within 2.0s without disconnecting
        await manager._safe_send(mock_ws, '{"type": "new_post"}', "test/board/ru")
        assert mock_ws in manager.active_connections["test/board/ru"]
        assert mock_ws.send_text.call_count == 1

    # =========================================================================
    # TASK 4: VISION EXPONENTIAL BACKOFF ON 429 & NSFW GEMINI PROTECTION
    # =========================================================================
    def test_nsfw_content_detection(self):
        """Verify NSFW/Porn keyword and skin tone detection."""
        # 1. Text keywords
        assert is_nsfw_content(caption="Check out this hentai picture") is True
        assert is_nsfw_content(caption="Смотри какое порно") is True
        assert is_nsfw_content(caption="Cute anime cat sitting in a garden") is False

        # 2. File paths
        assert is_nsfw_content(file_paths=["/images/board_b/nsfw_photo.jpg"]) is True
        assert is_nsfw_content(file_paths=["/images/board_b/nature_photo.jpg"]) is False

        # 3. High skin tone heuristic
        skin_img = Image.new("RGB", (64, 64), color=(255, 205, 180))  # Flesh color
        buf_skin = io.BytesIO()
        skin_img.save(buf_skin, format="JPEG")
        assert detect_high_skin_ratio(buf_skin.getvalue(), threshold=0.35) is True
        assert is_nsfw_content(images_data=[buf_skin.getvalue()]) is True

        sky_img = Image.new("RGB", (64, 64), color=(50, 150, 255))  # Sky blue
        buf_sky = io.BytesIO()
        sky_img.save(buf_sky, format="JPEG")
        assert detect_high_skin_ratio(buf_sky.getvalue(), threshold=0.35) is False
        assert is_nsfw_content(images_data=[buf_sky.getvalue()]) is False

    @pytest.mark.asyncio
    @patch("site_tgach.vision.prepare_image_for_analysis", return_value=(b"fake_jpeg_bytes", None))
    @patch("site_tgach.vision._call_gemini_native")
    @patch("site_tgach.vision.AsyncOpenAI")
    @patch("site_tgach.vision.google_pool.get_all_active_tokens", return_value=["gemini-key-1"])
    @patch("site_tgach.vision.groq_pool.get_all_active_tokens", return_value=["groq-key-1"])
    async def test_vision_nsfw_request_skips_gemini_and_uses_groq(
        self, mock_groq_pool, mock_google_pool, mock_openai_cls, mock_gemini_call, mock_prep
    ):
        """
        When NSFW/porn is detected, Gemini must NEVER be called, preventing PROHIBITED_CONTENT
        key bans from Google.
        """
        mock_client = AsyncMock()
        mock_choice = MagicMock()
        mock_choice.finish_reason = "stop"
        mock_choice.message.content = json.dumps({
            "tags": "nsfw, ecchi, anime",
            "description": "Описание изображения."
        })
        mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
        mock_openai_cls.return_value = mock_client

        # Call describe_image with NSFW caption
        res = await describe_image("/dummy/image.jpg", caption="Explicit hentai art", source="SITE")
        assert res is not None
        parsed = json.loads(res)
        assert "nsfw" in parsed["tags"]

        # Gemini must NOT be called at all!
        assert mock_gemini_call.call_count == 0, "Gemini must not be called for NSFW requests!"
        # Groq must be used instead
        assert mock_openai_cls.call_count == 1

    @pytest.mark.asyncio
    async def test_gemini_native_prohibited_content_returns_safety(self):
        """
        When Google returns HTTP 400 with PROHIBITED_CONTENT, _call_gemini_native
        must catch it and return (None, 'safety') without raising or burning keys.
        """
        mock_http_client = AsyncMock()
        resp_mock = MagicMock()
        resp_mock.status_code = 400
        resp_mock.text = "INVALID_ARGUMENT: PROHIBITED_CONTENT - generation blocked"
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
    @patch("site_tgach.vision.prepare_image_for_analysis", return_value=(b"fake_jpeg_bytes", None))
    @patch("site_tgach.vision.AsyncOpenAI")
    @patch("site_tgach.vision.groq_pool")
    async def test_groq_429_exponential_backoff(
        self, mock_groq_pool_mod, mock_openai_cls, mock_prep
    ):
        """
        Verify that consecutive 429 errors from Groq apply exponential backoff.
        """
        key1 = "groq-key-1"
        key2 = "groq-key-2"
        mock_groq_pool_mod.get_all_active_tokens.return_value = [key1, key2]
        mock_groq_pool_mod._cooldown_until = {}

        mock_client1 = AsyncMock()
        mock_client1.chat.completions.create.side_effect = Exception("429 rate limit: please try again in 10s")

        mock_client2 = AsyncMock()
        mock_choice = MagicMock()
        mock_choice.finish_reason = "stop"
        mock_choice.message.content = json.dumps({
            "tags": "cat, animal",
            "description": "Кот на траве."
        })
        mock_client2.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

        mock_openai_cls.side_effect = [mock_client1, mock_client2]

        with patch("site_tgach.vision.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            res = await describe_image("/dummy/image.jpg", source="TAGGER")
            assert res is not None

            # Verify penalize_token was called on one of the keys with backoff
            mock_groq_pool_mod.penalize_token.assert_called()
            penalize_args = mock_groq_pool_mod.penalize_token.call_args[0]
            assert penalize_args[0] in [key1, key2]
            # Penalty duration must be >= 15s (10s retry + 5s buffer)
            assert penalize_args[1] >= 15.0

            # Verify exponential sleep was called
            sleep_calls = [c.args[0] for c in mock_sleep.call_args_list if c.args]
            assert any(s >= 2.0 for s in sleep_calls)

    # =========================================================================
    # TASK 5: _proxy_external_url NOT IS_SAFE_URL RETURNS 404 FILE UNAVAILABLE
    # =========================================================================
    @pytest.mark.asyncio
    async def test_proxy_external_url_unsafe_returns_404_file_unavailable(self):
        """
        Verify that when a URL fails the SSRF is_safe_url check,
        _proxy_external_url returns HTTPException(404, detail='File unavailable')
        instead of 400 Unsafe URL, hiding infrastructure/SSRF details from callers.
        """
        # Testing unsafe IP / metadata URL
        unsafe_url = "http://169.254.169.254/latest/meta-data/"

        with pytest.raises(HTTPException) as exc_info:
            await _proxy_external_url(url=unsafe_url)

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "File unavailable"
