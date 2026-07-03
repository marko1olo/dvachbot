import sys
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ["SECRET_KEY"] = "test-secret-key-12345"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import main

class TestFontsCacheInitBlock(unittest.TestCase):
    def setUp(self):
        # Clear the cache before each test
        main.FONTS_CACHE.clear()

    @patch('PIL.ImageFont.truetype')
    @patch('PIL.ImageFont.load_default')
    @patch('os.path.exists')
    def test_fonts_cache_initialization_success(self, mock_exists, mock_load_default, mock_truetype):
        mock_exists.return_value = True
        mock_truetype.return_value = "custom_font_loaded"

        main.init_fonts_cache()

        self.assertEqual(len(main.FONTS_CACHE), 4)
        self.assertTrue(all(f == "custom_font_loaded" for f in main.FONTS_CACHE))

    @patch('PIL.ImageFont.truetype')
    @patch('PIL.ImageFont.load_default')
    @patch('os.path.exists')
    def test_fonts_cache_initialization_no_fonts(self, mock_exists, mock_load_default, mock_truetype):
        mock_exists.return_value = False
        mock_load_default.return_value = "default_font_no_files"

        main.init_fonts_cache()

        self.assertEqual(main.FONTS_CACHE, ["default_font_no_files"])
        mock_load_default.assert_called_once()

    @patch('PIL.ImageFont.truetype')
    @patch('PIL.ImageFont.load_default')
    @patch('os.path.exists')
    def test_fonts_cache_initialization_exception(self, mock_exists, mock_load_default, mock_truetype):
        mock_exists.return_value = True
        mock_truetype.side_effect = Exception("Test exception simulating corrupt font file")
        mock_load_default.return_value = "default_font_fallback"

        main.init_fonts_cache()

        self.assertEqual(main.FONTS_CACHE, ["default_font_fallback"])
        mock_load_default.assert_called_once()

if __name__ == "__main__":
    unittest.main()
