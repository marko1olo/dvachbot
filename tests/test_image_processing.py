import unittest
from Dubsite_tgach.image_processing import encode_dc

class TestEncodeDC(unittest.TestCase):
    def test_encode_dc_zeros(self):
        """Test encoding with all zeros."""
        self.assertEqual(encode_dc([0.0, 0.0, 0.0]), "0000")

    def test_encode_dc_ones(self):
        """Test encoding with all ones."""
        self.assertEqual(encode_dc([1.0, 1.0, 1.0]), "TSUA")

    def test_encode_dc_halfs(self):
        """Test encoding with all halfs."""
        self.assertEqual(encode_dc([0.5, 0.5, 0.5]), "Eyb[")

    def test_encode_dc_clamping(self):
        """Test that values > 1 are clamped to 255 (value of 1.0) and values < 0 are clamped to 0."""
        self.assertEqual(encode_dc([2.0, -1.0, 0.5]), "TI=7")

if __name__ == '__main__':
    unittest.main()
