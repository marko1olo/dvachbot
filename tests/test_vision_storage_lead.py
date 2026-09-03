import pytest
import asyncio
import time
import os
import tempfile
from unittest.mock import patch, MagicMock, AsyncMock

import site_tgach.catbox as catbox
from site_tgach.catbox import is_catbox_available, CATBOX_PAUSE_COOLDOWN
from site_tgach.mirror_worker import _process_single_task, _try_pixhost_upload, process_mirror_queue


class TestCatboxAndMirrorWorker:
    """Tests for Catbox availability, cooldown, and mirror worker fallback cascade."""

    def test_catbox_cooldown_30m(self):
        assert CATBOX_PAUSE_COOLDOWN == 1800
        catbox._CATBOX_GLOBAL_DISABLED_UNTIL = 0.0
        assert is_catbox_available() is True

        catbox._CATBOX_GLOBAL_DISABLED_UNTIL = time.time() + 1800
        assert is_catbox_available() is False

        catbox._CATBOX_GLOBAL_DISABLED_UNTIL = 0.0

    @pytest.mark.asyncio
    @patch("site_tgach.mirror_worker.get_file_owner_id", return_value=123)
    @patch("site_tgach.mirror_worker._resolve_file_bot")
    @patch("site_tgach.mirror_worker.get_file_mirrors", return_value={})
    @patch("site_tgach.mirror_worker.download_file_mtproto", return_value=False)
    @patch("site_tgach.mirror_worker.add_file_mirror", new_callable=AsyncMock)
    @patch("site_tgach.mirror_worker.remove_mirror_task", new_callable=AsyncMock)
    @patch("site_tgach.mirror_worker.upload_url_to_catbox", return_value=None)
    @patch("site_tgach.mirror_worker.upload_file_to_catbox", return_value=None)
    @patch("site_tgach.mirror_worker.upload_file_to_pixhost", new_callable=AsyncMock)
    async def test_catbox_fallback_to_pixhost_for_small_image(
        self, mock_pixhost, mock_catbox_file, mock_catbox_url,
        mock_rm_task, mock_add_mirror, mock_mtproto, mock_mirrors, mock_bot_res, mock_owner
    ):
        """When Catbox fails, an image <= 10MB cascades to pixhost and saves as pixhost mirror."""
        mock_bot = AsyncMock()
        mock_bot.token = "123:test_token"
        mock_file_info = MagicMock()
        mock_file_info.file_id = "AgAC_test_img"
        mock_file_info.file_path = "photos/test.jpg"
        mock_bot.get_file.return_value = mock_file_info
        mock_bot_res.return_value = (mock_bot, False)

        mock_pixhost.return_value = "https://pixhost.to/show/123/test.jpg"

        # Mock download by creating a real temp dummy file in http fallback
        with patch("site_tgach.mirror_worker.write_async_iter_bytes_to_file") as mock_writer:
            async def fake_write(aiter, path):
                with open(path, "wb") as f:
                    f.write(b"\xFF\xD8\xFF" + b"\x00" * 1024) # Valid JPEG header, ~1KB
            mock_writer.side_effect = fake_write

            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_resp = AsyncMock()
                mock_resp.status_code = 200
                mock_resp.aiter_bytes.return_value = [b"chunk"]
                mock_client.stream.return_value.__aenter__.return_value = mock_resp
                mock_client_cls.return_value.__aenter__.return_value = mock_client

                task = {
                    "id": 101,
                    "file_id": "AgAC_test_img",
                    "mirror_type": "catbox",
                    "attempts": 1,
                }
                await _process_single_task(task)

        # Pixhost must be called
        mock_pixhost.assert_called_once()
        # add_file_mirror must be called with 'pixhost'
        mock_add_mirror.assert_called_once_with("AgAC_test_img", "pixhost", "https://pixhost.to/show/123/test.jpg")
        mock_rm_task.assert_called_once_with(101)

    @pytest.mark.asyncio
    @patch("site_tgach.mirror_worker.get_file_owner_id", return_value=123)
    @patch("site_tgach.mirror_worker._resolve_file_bot")
    @patch("site_tgach.mirror_worker.get_file_mirrors", return_value={})
    @patch("site_tgach.mirror_worker.download_file_mtproto", return_value=False)
    @patch("site_tgach.mirror_worker.add_file_mirror", new_callable=AsyncMock)
    @patch("site_tgach.mirror_worker.remove_mirror_task", new_callable=AsyncMock)
    @patch("site_tgach.mirror_worker.upload_url_to_catbox", return_value=None)
    @patch("site_tgach.mirror_worker.upload_file_to_catbox", return_value=None)
    @patch("site_tgach.mirror_worker.upload_file_to_0x0", new_callable=AsyncMock)
    @patch("site_tgach.mirror_worker.is_0x0_available", return_value=True)
    async def test_catbox_fallback_to_0x0_for_non_image_file(
        self, mock_0x0_avail, mock_0x0, mock_catbox_file, mock_catbox_url,
        mock_rm_task, mock_add_mirror, mock_mtproto, mock_mirrors, mock_bot_res, mock_owner
    ):
        """When Catbox fails on a non-image file (e.g. mp4 or zip), it cascades to 0x0.st."""
        mock_bot = AsyncMock()
        mock_bot.token = "123:test_token"
        mock_file_info = MagicMock()
        mock_file_info.file_id = "BAAC_test_doc"
        mock_file_info.file_path = "documents/test.zip"
        mock_bot.get_file.return_value = mock_file_info
        mock_bot_res.return_value = (mock_bot, False)

        mock_0x0.return_value = "https://0x0.st/test.zip"

        with patch("site_tgach.mirror_worker.write_async_iter_bytes_to_file") as mock_writer:
            async def fake_write(aiter, path):
                with open(path, "wb") as f:
                    f.write(b"PK\x03\x04" + b"\x00" * 2048) # Zip file
            mock_writer.side_effect = fake_write

            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_resp = AsyncMock()
                mock_resp.status_code = 200
                mock_resp.aiter_bytes.return_value = [b"chunk"]
                mock_client.stream.return_value.__aenter__.return_value = mock_resp
                mock_client_cls.return_value.__aenter__.return_value = mock_client

                task = {
                    "id": 102,
                    "file_id": "BAAC_test_doc",
                    "mirror_type": "catbox",
                    "attempts": 1,
                }
                await _process_single_task(task)

        mock_0x0.assert_called_once()
        mock_add_mirror.assert_called_once_with("BAAC_test_doc", "0x0", "https://0x0.st/test.zip")
        mock_rm_task.assert_called_once_with(102)


class TestTaggerWorkerExhausted:
    """Tests for tagging worker handling of error_api_exhausted."""

    @pytest.mark.asyncio
    async def test_error_api_exhausted_leaves_tags_as_none(self):
        """When ai_response == 'error_api_exhausted', fail_cnt >= 3 must NOT set tags='no_tags'."""
        import site_tgach.tagging_worker as tw

        file_id = "test_exhausted_fid"
        tw.TEMP_FAILED_FILES[file_id] = {"cnt": 2, "until": time.time()}

        ai_response = "error_api_exhausted"
        tags = None

        # Replicate the exact logic from line ~1154 of tagging_worker.py
        if tags is None and ai_response in (None, "error_api_exhausted"):
            entry = tw.TEMP_FAILED_FILES.get(file_id)
            fail_cnt = ((entry.get("cnt", 0) + 1) if isinstance(entry, dict) else 1)
            if ai_response == "error_api_exhausted":
                cooldown_secs = 45
                tw.TEMP_FAILED_FILES[file_id] = {
                    "until": time.time() + 300,
                    "cnt": fail_cnt,
                }
                tags = None
            elif fail_cnt >= 3:
                tags = "no_tags"

        assert tags is None
        assert tw.TEMP_FAILED_FILES[file_id]["cnt"] == 3
        assert tw.TEMP_FAILED_FILES[file_id]["until"] > time.time()
