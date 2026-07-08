import os
import sys
import unittest
from pathlib import Path
import asyncio

# Setup env variables before importing main modules if needed
os.environ["SECRET_KEY"] = "test"
os.environ["BOT_TOKEN"] = "test"
os.environ["OPENAI_API_KEY"] = "test"

# Setup asyncio loop for Pyrogram imports if they happen
try:
    asyncio.get_running_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Dubsite_tgach.image_processing import clean_tags_string

class TestCleanTagsString(unittest.TestCase):
    def test_clean_tags_string_parameterized(self):
        """Test clean_tags_string with various inputs using self.subTest()."""
        test_cases = [
            # None or empty
            (None, None),
            ("", None),

            # Whitespace-only strings
            ("   ", ""),
            ("\t\n", ""),

            # Normal tags
            ("tag1, tag2, tag3", "tag1, tag2, tag3"),
            ("anime, girl", "anime, girl"),

            # Whitespace removal
            ("  tag1   tag2  ", "tag1 tag2"),
            ("tag1\n\ttag2", "tag1 tag2"),

            # Consecutive commas
            ("tag1,,tag2", "tag1,tag2"),
            ("tag1,,,tag2", "tag1,,tag2"),

            # Spaced commas
            ("tag1, ,tag2", "tag1,tag2"),
            ("tag1 , , tag2", "tag1 , tag2"),
            ("tag1 ,  , tag2", "tag1 , tag2"),
            ("tag1,   ,tag2", "tag1,tag2"),

            # Leading/trailing commas and spaces
            (" ,tag1, ", ",tag1,"),
            (", tag1 , ", ", tag1 ,"),
            (" , , , ", ", ,")
        ]

        for input_text, expected_output in test_cases:
            with self.subTest(input_text=input_text, expected_output=expected_output):
                self.assertEqual(clean_tags_string(input_text), expected_output)

if __name__ == '__main__':
    unittest.main()
