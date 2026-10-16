import sys
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ["SECRET_KEY"] = "test"
os.environ["BOT_TOKEN"] = "test"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

class TestEncodeAC(unittest.TestCase):
    def setUp(self):
        self.patcher = patch.dict('sys.modules', {
            'common.task_manager': MagicMock(),
            'common.database': MagicMock(),
            'common.secret_redaction': MagicMock(),
            'common.bot_pool': MagicMock(),
            'common.board_config': MagicMock(),
            'site_tgach.catbox': MagicMock(),
            'site_tgach.huggingface': MagicMock(),
            'site_tgach.mtproto_client': MagicMock(),
            'common': MagicMock(),
            'imagehash': MagicMock(),
            'PIL': MagicMock(),
            'PIL.Image': MagicMock(),
            'bs4': MagicMock(),
            'fastapi': MagicMock(),
            'aiogram': MagicMock(),
            'aiogram.types': MagicMock(),
            'aiogram.exceptions': MagicMock(),
        })
        self.patcher.start()

        # Ensure the module is imported fresh with these mocks
        if 'Dubsite_tgach.image_processing' in sys.modules:
            del sys.modules['Dubsite_tgach.image_processing']

        from Dubsite_tgach.image_processing import encode_ac
        self.encode_ac = encode_ac

    def tearDown(self):
        self.patcher.stop()
        if 'Dubsite_tgach.image_processing' in sys.modules:
            del sys.modules['Dubsite_tgach.image_processing']

    def test_encode_ac_zeros(self):
        self.assertEqual(self.encode_ac([0.0, 0.0, 0.0], 1.0), "fQ")

    def test_encode_ac_negative_bounds(self):
        self.assertEqual(self.encode_ac([-1.0, -1.0, -1.0], 1.0), "00")

    def test_encode_ac_positive_bounds(self):
        self.assertEqual(self.encode_ac([1.0, 1.0, 1.0], 1.0), "~q")

    def test_encode_ac_mixed_values(self):
        self.assertEqual(self.encode_ac([-2.0, 0.0, 2.0], 2.0), "2N")
        self.assertEqual(self.encode_ac([-0.5, 0.1, 0.8], 1.0), "G0")

if __name__ == '__main__':
    unittest.main()
