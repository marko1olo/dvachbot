import unittest
from unittest.mock import patch

from site_tgach.huggingface import _upload_sync


class TestHuggingFaceUploadSync(unittest.TestCase):

    @patch("site_tgach.huggingface.hf_accounts.get_pair")
    @patch("site_tgach.huggingface.is_hf_repo_available")
    @patch("site_tgach.huggingface.HfApi")
    @patch("site_tgach.huggingface.clear_hf_failure")
    def test_upload_sync_success(self, mock_clear_failure, mock_hf_api, mock_is_available, mock_get_pair):
        # Mock credentials and repo availability
        mock_get_pair.return_value = ("test_token", "test_repo_id")
        mock_is_available.return_value = True

        # Mock successful upload
        mock_api_instance = mock_hf_api.return_value

        # Call the function
        result = _upload_sync(b"test data", "test_filename.txt")

        # Verify result and calls
        self.assertIsNotNone(result)
        self.assertTrue("test_repo_id" in result)
        self.assertTrue("test_filename.txt" in result)
        mock_api_instance.upload_file.assert_called_once()
        mock_clear_failure.assert_called_once_with("test_repo_id")

    @patch("site_tgach.huggingface.hf_accounts.get_pair")
    def test_upload_sync_no_credentials(self, mock_get_pair):
        # Mock missing credentials
        mock_get_pair.return_value = (None, None)

        result = _upload_sync(b"test data", "test_filename.txt")

        self.assertIsNone(result)

    @patch("site_tgach.huggingface.hf_accounts.get_pair")
    @patch("site_tgach.huggingface.is_hf_repo_available")
    @patch("site_tgach.huggingface.HfApi")
    @patch("site_tgach.huggingface.mark_hf_upload_failure")
    def test_upload_sync_upload_exception(self, mock_mark_failure, mock_hf_api, mock_is_available, mock_get_pair):
        # Mock credentials and repo availability
        mock_get_pair.return_value = ("test_token", "test_repo_id")
        mock_is_available.return_value = True

        # Mock exception during upload
        mock_api_instance = mock_hf_api.return_value
        mock_api_instance.upload_file.side_effect = Exception("Upload failed")

        # We need mark_hf_upload_failure to return True to break the retry loop
        # so the test finishes without trying multiple strategies (which it would anyway,
        # but this ensures the exception path is fully taken and exits early as designed).
        mock_mark_failure.return_value = True

        result = _upload_sync(b"test data", "test_filename.txt")

        # Result should be None on failure
        self.assertIsNone(result)
        mock_mark_failure.assert_called_once()

if __name__ == "__main__":
    unittest.main()
