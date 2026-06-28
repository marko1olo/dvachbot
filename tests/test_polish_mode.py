import unittest
from polish_mode import polish_transform

class TestPolishMode(unittest.TestCase):
    def test_polish_transform_empty(self):
        res_type, text = polish_transform("")
        self.assertEqual(text, "")
        self.assertEqual(res_type, "text")

    def test_polish_transform_basic(self):
        # We need to test that it returns without raising exceptions
        text = "Это хороший телевизор"
        res_type, res_val = polish_transform(text)
        self.assertIn(res_type, ["text", "image"])

if __name__ == '__main__':
    unittest.main()
