import os
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import sys
import asyncio

try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

import site_tgach.hf_batcher as hf_batcher

class TestCleanupStaleTempDirs(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.orig_cwd = os.getcwd()
        os.chdir(self.tmpdir)

    def tearDown(self):
        os.chdir(self.orig_cwd)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_cleanup_stale_temp_dirs(self):
        # Create matching directories
        os.makedirs("temp_hf_123")
        os.makedirs("temp_hf_456")

        # Create non-matching directory
        os.makedirs("other_dir")

        # Create matching file (should not be deleted because it's not a dir)
        with open("temp_hf_file.txt", "w") as f:
            f.write("test")

        with patch.object(hf_batcher, "logger") as mock_logger:
            hf_batcher.cleanup_stale_temp_dirs()

            self.assertFalse(os.path.exists("temp_hf_123"))
            self.assertFalse(os.path.exists("temp_hf_456"))
            self.assertTrue(os.path.exists("other_dir"))
            self.assertTrue(os.path.exists("temp_hf_file.txt"))
            mock_logger.info.assert_called_with("🧹 Startup Cleanup: Removed 2 stale temp folders.")

    def test_cleanup_handles_exception(self):
        with patch.object(hf_batcher, "logger") as mock_logger:
            with patch("os.getcwd", side_effect=Exception("Test Exception")):
                hf_batcher.cleanup_stale_temp_dirs()
                mock_logger.error.assert_called_with("Startup cleanup error: Test Exception", exc_info=True)

    def test_cleanup_handles_rmtree_exception(self):
        os.makedirs("temp_hf_error")
        with patch.object(hf_batcher, "logger") as mock_logger:
            with patch("shutil.rmtree", side_effect=Exception("rmtree failed")):
                hf_batcher.cleanup_stale_temp_dirs()

                # It shouldn't crash, and it shouldn't log "Removed N" since count is 0
                mock_logger.info.assert_not_called()
                # The directory will still exist because rmtree was mocked
                self.assertTrue(os.path.exists("temp_hf_error"))

if __name__ == "__main__":
    unittest.main()
