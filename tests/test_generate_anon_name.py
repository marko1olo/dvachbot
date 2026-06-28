import os
import sys
import unittest
import random
import asyncio
from unittest.mock import MagicMock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Mock environment variables
os.environ["SECRET_KEY"] = "test"
os.environ["BOT_TOKEN"] = "test"
os.environ["OPENAI_API_KEY"] = "test"

# Create and set new event loop to avoid Pyrogram/asyncio errors
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# Mock required dependencies to allow main.py to be imported
sys.modules['httpx'] = MagicMock()
sys.modules['openai'] = MagicMock()
sys.modules['bs4'] = MagicMock()
sys.modules['boto3'] = MagicMock()
sys.modules['anthropic'] = MagicMock()
sys.modules['botocore'] = MagicMock()
sys.modules['botocore.exceptions'] = MagicMock()
sys.modules['botocore.client'] = MagicMock()
sys.modules['yookassa'] = MagicMock()
sys.modules['telethon'] = MagicMock()

from main import generate_anon_name, NICK_PREFIXES, NICK_SUFFIXES

class TestGenerateAnonName(unittest.TestCase):
    def test_deterministic_generation(self):
        user_id = 12345
        rng = random.Random(user_id)
        expected_prefix = rng.choice(NICK_PREFIXES)
        expected_suffix = rng.choice(NICK_SUFFIXES)
        expected_str = f"{expected_prefix}-{expected_suffix} (#{str(user_id)[-4:]})"
        self.assertEqual(generate_anon_name(user_id), expected_str)

    def test_zero_user_id(self):
        self.assertEqual(generate_anon_name(0), "Анонимус")

    def test_none_user_id(self):
        self.assertEqual(generate_anon_name(None), "Анонимус")

    def test_different_seeds(self):
        name1 = generate_anon_name(1)
        name2 = generate_anon_name(2)
        # Determinism check
        self.assertEqual(generate_anon_name(1), name1)
        self.assertEqual(generate_anon_name(2), name2)

    def test_short_user_id(self):
        user_id = 12
        rng = random.Random(user_id)
        expected_prefix = rng.choice(NICK_PREFIXES)
        expected_suffix = rng.choice(NICK_SUFFIXES)
        expected_str = f"{expected_prefix}-{expected_suffix} (#{user_id})"
        self.assertEqual(generate_anon_name(user_id), expected_str)


if __name__ == '__main__':
    unittest.main()
