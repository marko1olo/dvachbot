import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Ensure import paths work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class TestPolishMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # We patch PIL when the class is set up to allow importing the module safely
        cls.patcher = patch.dict('sys.modules', {
            'PIL': MagicMock(),
            'PIL.Image': MagicMock(),
            'PIL.ImageDraw': MagicMock(),
            'PIL.ImageFont': MagicMock()
        })
        cls.patcher.start()

        # Now import the module safely
        import polish_mode
        cls.polish_mode = polish_mode

    @classmethod
    def tearDownClass(cls):
        cls.patcher.stop()

    def test_empty_string(self):
        result = self.polish_mode.polish_transform("")
        self.assertEqual(result, ('text', ""))

    @patch('polish_mode.random.random')
    @patch('polish_mode.create_visual_post')
    def test_short_message_no_kurwa(self, mock_visual, mock_random):
        mock_random.return_value = 0.5  # Greater than 0.4

        result = self.polish_mode.polish_transform("short msg")
        self.assertEqual(result, ('text', "short msg"))
        mock_visual.assert_not_called()

    @patch('polish_mode.random.random')
    @patch('polish_mode.create_visual_post')
    def test_short_message_kurwa_and_visual(self, mock_visual, mock_random):
        mock_random.return_value = 0.1  # Less than 0.4 and 0.25
        mock_visual.return_value = b"image_data"

        result = self.polish_mode.polish_transform("short msg", "header")

        self.assertEqual(result, ('image', b"image_data"))
        mock_visual.assert_called_once_with('polish', "short msg, kurwa", "header")

    @patch('polish_mode.random.random')
    @patch('polish_mode.create_visual_post')
    def test_long_message(self, mock_visual, mock_random):
        mock_random.return_value = 0.9
        mock_visual.return_value = None

        result = self.polish_mode.polish_transform("this is a longer message to test the fallback path without visual.")

        self.assertEqual(result[0], 'text')
        self.assertTrue(isinstance(result[1], str))

if __name__ == '__main__':
    unittest.main()
