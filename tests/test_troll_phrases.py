import unittest
from unittest.mock import patch
import troll_phrases

class TestTrollPhrases(unittest.TestCase):
    def test_context_chain(self):
        phrase = troll_phrases.get_random_troll_phrase(context_type="chain")
        self.assertIn(phrase, troll_phrases.CHAIN_PHRASES)

    def test_context_speed(self):
        phrase = troll_phrases.get_random_troll_phrase(context_type="speed")
        self.assertIn(phrase, troll_phrases.SPEED_PHRASES)

    def test_context_media(self):
        phrase = troll_phrases.get_random_troll_phrase(context_type="media")
        self.assertIn(phrase, troll_phrases.MEDIA_PHRASES)

    @patch('troll_phrases.random.random')
    @patch('troll_phrases.random.choice')
    def test_normal_short_phrase_no_emoji(self, mock_choice, mock_random):
        # 1st: 0.1 (< 0.2, triggers short phrase)
        # 2nd: 0.5 (for emoji prob, not > 0.7, so no emoji)
        # 3rd: 0.9 (for quote prob, if called, but won't be without quote_text)
        mock_random.side_effect = [0.1, 0.5, 0.9]
        mock_choice.return_value = "Short"

        phrase = troll_phrases.get_random_troll_phrase()
        self.assertEqual(phrase, "Short")

    @patch('troll_phrases.random.random')
    @patch('troll_phrases.random.choice')
    def test_normal_short_phrase_with_emoji(self, mock_choice, mock_random):
        mock_random.side_effect = [0.1, 0.8, 0.9]
        mock_choice.side_effect = ["Short", "🤡"]

        phrase = troll_phrases.get_random_troll_phrase()
        self.assertEqual(phrase, "Short🤡")

    @patch('troll_phrases.random.random')
    @patch('troll_phrases.random.choice')
    def test_normal_unique_phrase(self, mock_choice, mock_random):
        mock_random.side_effect = [0.3, 0.9] # 0.2 <= x < 0.35
        mock_choice.return_value = "Unique phrase"

        phrase = troll_phrases.get_random_troll_phrase()
        self.assertEqual(phrase, "Unique phrase")

    @patch('troll_phrases.random.random')
    @patch('troll_phrases.random.randint')
    @patch('troll_phrases.random.choice')
    def test_normal_emojis_only(self, mock_choice, mock_randint, mock_random):
        mock_random.side_effect = [0.4, 0.9] # 0.35 <= x < 0.45
        mock_choice.return_value = "😂"
        mock_randint.return_value = 3

        phrase = troll_phrases.get_random_troll_phrase()
        self.assertEqual(phrase, "😂😂😂")

    @patch('troll_phrases.random.random')
    @patch('troll_phrases.random.randint')
    @patch('troll_phrases.random.choice')
    def test_normal_pattern_1(self, mock_choice, mock_randint, mock_random):
        # 1st random: 0.5 (> 0.45)
        # 2nd random: 0.5 (for emoji, > 0.4 -> has emoji)
        # 3rd random: 0.9 (for quote prob, if it had quote)
        mock_random.side_effect = [0.5, 0.5, 0.9]
        mock_randint.return_value = 1 # pattern 1

        # choices:
        # 1. PREFIXES -> "pref"
        # 2. SUBJECTS -> "subj"
        # 3. ACTIONS -> "act"
        # 4. ADVICES -> "adv" (Unused in pattern 1, but still chosen unconditionally)
        # 5. EMOJIS -> "emj" (Chosen because random > 0.4)
        mock_choice.side_effect = ["pref", "subj", "act", "adv", "emj"]

        phrase = troll_phrases.get_random_troll_phrase()
        self.assertEqual(phrase, "Pref subj act emj") # Auto capitalization

    @patch('troll_phrases.random.random')
    @patch('troll_phrases.random.randint')
    @patch('troll_phrases.random.choice')
    def test_normal_pattern_8(self, mock_choice, mock_randint, mock_random):
        mock_random.side_effect = [0.5, 0.1, 0.9] # no emoji (0.1 <= 0.4)
        mock_randint.return_value = 8 # pattern 8

        # choices:
        # 1. PREFIXES -> "pref,"
        # 2. SUBJECTS -> "subj"
        # 3. ACTIONS -> "act1"
        # 4. ADVICES -> "adv"
        # (EMOJIS not chosen because random <= 0.4)
        # 5. act2 (ACTIONS) -> "act1" (Matches act, so loops)
        # 6. act2 (ACTIONS) -> "act2" (Different, loop exits)
        mock_choice.side_effect = ["pref,", "subj", "act1", "adv", "act1", "act2"]

        phrase = troll_phrases.get_random_troll_phrase()
        self.assertEqual(phrase, "Pref, subj act1, а потом act2. adv")

    @patch('troll_phrases.random.random')
    @patch('troll_phrases.random.choice')
    def test_quote_addition(self, mock_choice, mock_random):
        # random for normal generation: 0.3 (unique phrase)
        # random for quote addition: 0.2 (< 0.4)
        mock_random.side_effect = [0.3, 0.2]
        mock_choice.side_effect = ["Test phrase", "This is a quote"]

        quote_text = "This is a quote. And another sentence."
        phrase = troll_phrases.get_random_troll_phrase(quote_text=quote_text)

        # Note: troll_phrases.py explicitly returns literal '\\n\\n' rather than standard newlines.
        self.assertEqual(phrase, ">This is a quote\\n\\nTest phrase")

    @patch('troll_phrases.random.random')
    @patch('troll_phrases.random.choice')
    def test_long_quote_truncation(self, mock_choice, mock_random):
        mock_random.side_effect = [0.3, 0.2]

        long_sentence = "A" * 150
        mock_choice.side_effect = ["Test phrase", long_sentence]

        quote_text = long_sentence
        phrase = troll_phrases.get_random_troll_phrase(quote_text=quote_text)

        expected_quote = ("A" * 97) + "..."
        # Note: troll_phrases.py explicitly returns literal '\\n\\n' rather than standard newlines.
        self.assertEqual(phrase, f">{expected_quote}\\n\\nTest phrase")

    def test_fuzz_normal_generation(self):
        for _ in range(100):
            troll_phrases.get_random_troll_phrase()
            troll_phrases.get_random_troll_phrase(quote_text="Some sentence here. Another one there.")

if __name__ == '__main__':
    unittest.main()
