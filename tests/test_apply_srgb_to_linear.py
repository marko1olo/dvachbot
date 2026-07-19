import sys
import os
import unittest
from unittest.mock import MagicMock, patch
import math

os.environ["SECRET_KEY"] = "test"
os.environ["BOT_TOKEN"] = "test"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

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
    from Dubsite_tgach.image_processing import apply_srgb_to_linear, sign_pow

class TestApplySrgbToLinear(unittest.TestCase):
    def test_apply_srgb_to_linear_low(self):
        # 0.04045 * 255 = 10.31475. So input values <= ~10.31475 take the first branch.
        self.assertAlmostEqual(apply_srgb_to_linear(0), 0.0, places=5)
        self.assertAlmostEqual(apply_srgb_to_linear(10), (10/255.0)/12.92, places=5)
        self.assertAlmostEqual(apply_srgb_to_linear(10.31475), (10.31475/255.0)/12.92, places=5)

    def test_apply_srgb_to_linear_high(self):
        # Input values > 10.31475 take the second branch.
        v = 255 / 255.0
        expected = ((v + 0.055) / 1.055) ** 2.4
        self.assertAlmostEqual(apply_srgb_to_linear(255), expected, places=5)

        v = 128 / 255.0
        expected = ((v + 0.055) / 1.055) ** 2.4
        self.assertAlmostEqual(apply_srgb_to_linear(128), expected, places=5)

        v = 11 / 255.0
        expected = ((v + 0.055) / 1.055) ** 2.4
        self.assertAlmostEqual(apply_srgb_to_linear(11), expected, places=5)

    def test_apply_srgb_to_linear_edge_cases(self):
        # Extremely small positive values
        self.assertAlmostEqual(apply_srgb_to_linear(0.001), (0.001/255.0)/12.92, places=5)

        # Test values just above and below the threshold
        val_below = 10.31474
        self.assertAlmostEqual(apply_srgb_to_linear(val_below), (val_below/255.0)/12.92, places=5)

        val_above = 10.31476
        v_above = val_above / 255.0
        expected = ((v_above + 0.055) / 1.055) ** 2.4
        self.assertAlmostEqual(apply_srgb_to_linear(val_above), expected, places=5)

class TestSignPow(unittest.TestCase):
    def test_sign_pow_positive(self):
        self.assertAlmostEqual(sign_pow(2, 2), 4)
        self.assertAlmostEqual(sign_pow(2, 3), 8)

    def test_sign_pow_negative(self):
        self.assertAlmostEqual(sign_pow(-2, 2), -4)
        self.assertAlmostEqual(sign_pow(-2, 3), -8)

    def test_sign_pow_zero(self):
        self.assertEqual(sign_pow(0, 2), 0)

    def test_sign_pow_fractional_exp(self):
        self.assertAlmostEqual(sign_pow(4, 0.5), 2)
        self.assertAlmostEqual(sign_pow(-4, 0.5), -2)

if __name__ == '__main__':
    unittest.main()
