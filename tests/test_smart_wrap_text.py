import unittest
import sys
from unittest.mock import MagicMock, patch

class MockModule(MagicMock):
    @classmethod
    def __getattr__(cls, name):
        return MagicMock()

# Since mocking matplotlib in setUp using patch.dict was causing numpy re-import issues,
# let's mock it but avoid mocking matplotlib if it's already properly installed and functional,
# or mock the specific dependencies locally safely.
# Wait, numpy import error is "cannot load module more than once per process", which happens
# when we mess with sys.modules and reload submodules inconsistently.

class TestSmartWrapText(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # We need to import main.py carefully just once for all tests.
        cls.mock_deps = {
            'psutil': MockModule(),
            'aiosqlite': MockModule(),
            'ujson': MockModule(),
            'pyrogram': MockModule(),
            'openai': MockModule(),
            'huggingface_hub': MockModule(),
            'celery': MockModule(),
            'tenacity': MockModule(),
            'imagehash': MockModule(),
        }

        # apply the patch just during the import
        with patch.dict('sys.modules', cls.mock_deps):
            from main import smart_wrap_text
            cls.smart_wrap_text = staticmethod(smart_wrap_text)

    def setUp(self):
        self.mock_draw = MagicMock()
        self.mock_font = MagicMock()

        def mock_textlength(text, font=None):
            return len(text) * 10

        self.mock_draw.textlength.side_effect = mock_textlength

    def test_empty_string(self):
        res = self.smart_wrap_text(self.mock_draw, "", self.mock_font, 100)
        self.assertEqual(res, "")

    def test_single_line_fits(self):
        res = self.smart_wrap_text(self.mock_draw, "Hello world", self.mock_font, 200)
        self.assertEqual(res, "Hello world")

    def test_single_line_wrap(self):
        res = self.smart_wrap_text(self.mock_draw, "Hello world", self.mock_font, 60)
        self.assertEqual(res, "Hello\nworld")

    def test_multiple_lines_wrap(self):
        res = self.smart_wrap_text(self.mock_draw, "One two three four five", self.mock_font, 90)
        self.assertEqual(res, "One two\nthree\nfour\nfive")

    def test_preserves_empty_lines(self):
        res = self.smart_wrap_text(self.mock_draw, "Hello\n\nworld", self.mock_font, 200)
        self.assertEqual(res, "Hello\n\nworld")

    def test_word_longer_than_max_width(self):
        res = self.smart_wrap_text(self.mock_draw, "Extralongword", self.mock_font, 100)
        self.assertEqual(res, "\nExtralongword")

if __name__ == '__main__':
    unittest.main()
