import unittest
from unittest.mock import patch
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mode_punchup import _add_signature, punch_up_mode_text

class TestModePunchupSignature(unittest.TestCase):
    def test_no_signatures(self):
        text = "Hello world"
        # No signatures provided
        self.assertEqual(_add_signature(text, {}), text)
        # Empty signatures list
        self.assertEqual(_add_signature(text, {"signatures": []}), text)

    def test_max_text_length_exceeded(self):
        text = "A" * 1201
        profile = {"signatures": ["- The Boss"]}
        # Default max length is 1200
        self.assertEqual(_add_signature(text, profile), text)

        # Custom max length
        text = "A" * 501
        profile = {"signatures": ["- The Boss"], "max_text_for_signature": 500}
        self.assertEqual(_add_signature(text, profile), text)

        # Custom max length not exceeded
        text = "A" * 499
        with patch("random.random", return_value=0.1):
            with patch("random.choice", return_value="- The Boss"):
                self.assertEqual(_add_signature(text, profile), f"{text}. - The Boss")

    @patch("random.random")
    def test_random_chance_fails(self, mock_random):
        text = "Hello world"
        profile = {"signatures": ["- The Boss"]}
        # Default signature_chance is 0.16
        # If random.random() > 0.16, returns text
        mock_random.return_value = 0.5
        self.assertEqual(_add_signature(text, profile), text)

        # Custom signature chance
        profile["signature_chance"] = 0.8
        mock_random.return_value = 0.9
        self.assertEqual(_add_signature(text, profile), text)

    @patch("random.random")
    @patch("random.choice")
    def test_signature_already_in_text(self, mock_choice, mock_random):
        text = "Hello world. - The Boss"
        profile = {"signatures": ["- The Boss"]}
        mock_random.return_value = 0.1
        mock_choice.return_value = "- The Boss"

        self.assertEqual(_add_signature(text, profile), text)

    @patch("random.random")
    @patch("random.choice")
    def test_text_ends_with_punctuation(self, mock_choice, mock_random):
        profile = {"signatures": ["- The Boss"]}
        mock_random.return_value = 0.1
        mock_choice.return_value = "- The Boss"

        punctuations = [".", "!", "?", "...", "]"]
        for p in punctuations:
            text = f"Hello world{p}"
            with self.subTest(punctuation=p):
                self.assertEqual(_add_signature(text, profile), f"{text} - The Boss")

    @patch("random.random")
    @patch("random.choice")
    def test_text_does_not_end_with_punctuation(self, mock_choice, mock_random):
        profile = {"signatures": ["- The Boss"]}
        mock_random.return_value = 0.1
        mock_choice.return_value = "- The Boss"

        text = "Hello world"
        self.assertEqual(_add_signature(text, profile), f"{text}. - The Boss")

        text = "Hello world,"
        self.assertEqual(_add_signature(text, profile), f"{text}. - The Boss")



class TestPunchUpModeText(unittest.TestCase):
    def test_no_mode_key(self):
        text = "Hello world"
        self.assertEqual(punch_up_mode_text(text, None), text)
        self.assertEqual(punch_up_mode_text(text, ""), text)

    @patch.dict("mode_punchup.MODE_PUNCHUP_PROFILES", {}, clear=True)
    def test_mode_key_not_found(self):
        text = "Hello world"
        self.assertEqual(punch_up_mode_text(text, "invalid_mode"), text)

    @patch.dict("mode_punchup.MODE_PUNCHUP_PROFILES", {"valid_mode": {"replace_chance": 0.5}}, clear=True)
    @patch("mode_punchup._decorate")
    def test_mode_key_found(self, mock_decorate):
        text = "Hello world"
        mock_decorate.return_value = "Decorated text"

        result = punch_up_mode_text(text, "valid_mode")

        self.assertEqual(result, "Decorated text")
        mock_decorate.assert_called_once_with(text, {"replace_chance": 0.5})

if __name__ == "__main__":
    unittest.main()
