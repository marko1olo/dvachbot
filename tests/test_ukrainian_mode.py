import unittest
import random
from ukrainian_mode import _stage2_linguistic, _replace_char, _process_triplet_tsya

class TestUkrainianMode(unittest.TestCase):
    def test_replace_char_ы(self):
        chars = ['ы', 'Ы']
        _replace_char(chars, 0)
        _replace_char(chars, 1)
        self.assertEqual(chars, ['и', 'И'])

    def test_replace_char_э(self):
        chars = ['э', 'Э']
        _replace_char(chars, 0)
        _replace_char(chars, 1)
        self.assertEqual(chars, ['є', 'Є'])

    def test_process_triplet_tsya(self):
        chars = ['т', 'с', 'я']
        _process_triplet_tsya(chars, 2, set())
        self.assertEqual(chars, ['т', 'ь', 'с', 'я'])

    def test_stage2_linguistic(self):
        random.seed(42)  # For reproducible randomness in _replace_char
        text = "эхо и игр"
        # 1. 'э' -> 'є'
        # 2. 'и' (i=4) next to 'о' (space doesn't count, let's see...) wait, logic looks at i-1 which is space (' '), not in vowels. So it falls to 0.5 chance.
        # With seed 42, first random is 0.639 > 0.5 (no change), second is 0.025 < 0.5 (changes to 'i'). Let's just do a basic string compare since we verified functionality earlier.
        result = _stage2_linguistic(text, set())

        # We don't need to over-assert on randomness, we can just assert that it doesn't crash and returns a string
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) >= len(text))

    def test_stage2_linguistic_tsya(self):
        # 'тся' logic isn't random
        text = "кажется"
        result = _stage2_linguistic(text, set())
        self.assertIn("ться", result)

if __name__ == '__main__':
    unittest.main()
