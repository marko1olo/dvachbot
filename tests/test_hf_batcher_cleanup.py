import os
import shutil
import tempfile
import unittest
from unittest.mock import patch
from Dubsite_tgach.hf_batcher import cleanup_stale_temp_dirs

class TestCleanupStaleTempDirs(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.orig_cwd = os.getcwd()
        os.chdir(self.tmpdir)

    def tearDown(self):
        os.chdir(self.orig_cwd)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch("Dubsite_tgach.hf_batcher.logger")
    def test_cleanup_stale_temp_dirs(self, mock_logger):
        # Create matching directories
        os.makedirs("temp_hf_123")
        os.makedirs("temp_hf_456")

        # Create non-matching directory
        os.makedirs("other_dir")

        # Create matching file (should not be deleted because it's not a dir)
        with open("temp_hf_file.txt", "w") as f:
            f.write("test")

        cleanup_stale_temp_dirs()

        self.assertFalse(os.path.exists("temp_hf_123"))
        self.assertFalse(os.path.exists("temp_hf_456"))
        self.assertTrue(os.path.exists("other_dir"))
        self.assertTrue(os.path.exists("temp_hf_file.txt"))
        mock_logger.info.assert_called_with("🧹 Startup Cleanup: Removed 2 stale temp folders.")

    @patch("Dubsite_tgach.hf_batcher.logger")
    def test_cleanup_handles_exception(self, mock_logger):
        with patch("os.getcwd", side_effect=Exception("Test Exception")):
            cleanup_stale_temp_dirs()
            mock_logger.error.assert_called_with("Startup cleanup error: Test Exception")

    @patch("Dubsite_tgach.hf_batcher.logger")
    @patch("Dubsite_tgach.hf_batcher.shutil.rmtree")
    def test_cleanup_handles_rmtree_exception(self, mock_rmtree, mock_logger):
        os.makedirs("temp_hf_error")
        mock_rmtree.side_effect = Exception("rmtree failed")

        cleanup_stale_temp_dirs()

        # It shouldn't crash, and it shouldn't log "Removed N" since count is 0
        mock_logger.info.assert_not_called()
        # The directory will still exist because rmtree was mocked
        self.assertTrue(os.path.exists("temp_hf_error"))

if __name__ == "__main__":
    unittest.main()
