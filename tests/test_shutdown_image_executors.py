import unittest
from unittest.mock import MagicMock
import site_tgach.image_processing as image_processing

class TestShutdownImageExecutors(unittest.TestCase):
    def setUp(self):
        # Save original state
        self.orig_process_pool = image_processing._process_pool
        self.orig_thumb_process_pool = image_processing._thumb_process_pool

    def tearDown(self):
        # Restore original state
        image_processing._process_pool = self.orig_process_pool
        image_processing._thumb_process_pool = self.orig_thumb_process_pool

    def test_shutdown_executors_both_exist(self):
        # Setup mocks
        mock_process_pool = MagicMock()
        mock_thumb_pool = MagicMock()

        image_processing._process_pool = mock_process_pool
        image_processing._thumb_process_pool = mock_thumb_pool

        # Call the function
        image_processing.shutdown_image_executors()

        # Verify
        mock_process_pool.shutdown.assert_called_once_with(wait=False, cancel_futures=True)
        mock_thumb_pool.shutdown.assert_called_once_with(wait=False, cancel_futures=True)
        self.assertIsNone(image_processing._process_pool)
        self.assertIsNone(image_processing._thumb_process_pool)

    def test_shutdown_executors_one_is_none(self):
        # Setup mocks
        mock_thumb_pool = MagicMock()

        image_processing._process_pool = None
        image_processing._thumb_process_pool = mock_thumb_pool

        # Call the function
        image_processing.shutdown_image_executors()

        # Verify
        mock_thumb_pool.shutdown.assert_called_once_with(wait=False, cancel_futures=True)
        self.assertIsNone(image_processing._process_pool)
        self.assertIsNone(image_processing._thumb_process_pool)

    def test_shutdown_executors_both_are_none(self):
        # Setup mocks
        image_processing._process_pool = None
        image_processing._thumb_process_pool = None

        # Call the function
        image_processing.shutdown_image_executors()

        # Verify
        self.assertIsNone(image_processing._process_pool)
        self.assertIsNone(image_processing._thumb_process_pool)

if __name__ == '__main__':
    unittest.main()
