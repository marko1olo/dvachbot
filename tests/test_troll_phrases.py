import unittest
from unittest.mock import patch
from troll_phrases import get_random_troll_phrase, CHAIN_PHRASES, SPEED_PHRASES, MEDIA_PHRASES

class TestTrollPhrases(unittest.TestCase):
    def test_get_random_troll_phrase_chain(self):
        phrase = get_random_troll_phrase(context_type="chain")
        self.assertIn(phrase, CHAIN_PHRASES)

    def test_get_random_troll_phrase_speed(self):
        phrase = get_random_troll_phrase(context_type="speed")
        self.assertIn(phrase, SPEED_PHRASES)

    def test_get_random_troll_phrase_media(self):
        phrase = get_random_troll_phrase(context_type="media")
        self.assertIn(phrase, MEDIA_PHRASES)

    def test_get_random_troll_phrase_normal(self):
        phrase = get_random_troll_phrase(context_type="normal")
        self.assertIsInstance(phrase, str)
        self.assertGreater(len(phrase), 0)

    @patch('random.random')
    def test_get_random_troll_phrase_with_quote(self, mock_random):
        # Force the condition random.random() < 0.4 to be true in _add_quote
        mock_random.return_value = 0.1
        quote_text = "This is a sentence. This is another sentence. Short."
        phrase = get_random_troll_phrase(context_type="normal", quote_text=quote_text)
        self.assertTrue(phrase.startswith(">"))
        self.assertIn("\\n\\n", phrase)

if __name__ == '__main__':
    unittest.main()
