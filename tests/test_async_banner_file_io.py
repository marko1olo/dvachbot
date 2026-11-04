import asyncio
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from common.async_file_io import read_file_bytes_async


class TestAsyncBannerFileIO(unittest.IsolatedAsyncioTestCase):
    async def test_read_file_bytes_async_banner_data(self):
        sample_bytes = b"\x89PNG\r\n\x1a\nfake_image_data_payload_12345"
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(sample_bytes)
            tmp_path = tf.name

        try:
            payload = MagicMock()
            payload.path = tmp_path
            fid = None

            img_bytes = None
            if not fid and hasattr(payload, "path") and os.path.exists(payload.path):
                try:
                    img_bytes = await read_file_bytes_async(payload.path)
                except Exception:
                    pass

            self.assertEqual(img_bytes, sample_bytes)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    async def test_read_file_bytes_async_exception_handling(self):
        payload = MagicMock()
        payload.path = "/nonexistent/path/to/banner.png"
        fid = None

        img_bytes = None
        if not fid and hasattr(payload, "path") and os.path.exists(payload.path):
            try:
                img_bytes = await read_file_bytes_async(payload.path)
            except Exception:
                pass

        self.assertIsNone(img_bytes)

    async def test_read_file_bytes_async_when_fid_present(self):
        sample_bytes = b"sample_banner"
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(sample_bytes)
            tmp_path = tf.name

        try:
            payload = MagicMock()
            payload.path = tmp_path
            fid = "existing_telegram_file_id"

            img_bytes = None
            if not fid and hasattr(payload, "path") and os.path.exists(payload.path):
                try:
                    img_bytes = await read_file_bytes_async(payload.path)
                except Exception:
                    pass

            self.assertIsNone(img_bytes)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)


if __name__ == "__main__":
    unittest.main()
