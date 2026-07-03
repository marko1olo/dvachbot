import sys
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ["SECRET_KEY"] = "test"
os.environ["BOT_TOKEN"] = "test"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Using mock.patch.dict instead to not pollute sys.modules globally and permanently
with patch.dict('sys.modules', {
    'common.task_manager': MagicMock(),
    'common.database': MagicMock(),
    'common.secret_redaction': MagicMock(),
    'common.bot_pool': MagicMock(),
    'common.board_config': MagicMock(),
    'site_tgach.catbox': MagicMock(),
    'site_tgach.huggingface': MagicMock(),
    'site_tgach.mtproto_client': MagicMock(),
    'common': MagicMock(),
}):
    from Dubsite_tgach.image_processing import encode_83

class TestEncode83(unittest.TestCase):
    def test_encode_zero(self):
        self.assertEqual(encode_83(0, 1), "0")
        self.assertEqual(encode_83(0, 2), "00")
        self.assertEqual(encode_83(0, 3), "000")

    def test_encode_single_char(self):
        self.assertEqual(encode_83(1, 1), "1")
        self.assertEqual(encode_83(10, 1), "A")
        self.assertEqual(encode_83(36, 1), "a")
        self.assertEqual(encode_83(82, 1), "~")

    def test_encode_multiple_chars(self):
        self.assertEqual(encode_83(83, 2), "10")
        self.assertEqual(encode_83(83 * 83 - 1, 2), "~~")

    def test_encode_larger_values(self):
        self.assertEqual(encode_83(6889, 3), "100")
        self.assertEqual(encode_83(123456789, 5), "2n[;G")

    def test_encode_negative_length(self):
        # Even though a negative length isn't normal, joining an empty generator yields ""
        self.assertEqual(encode_83(123, -1), "")

if __name__ == '__main__':
    unittest.main()
