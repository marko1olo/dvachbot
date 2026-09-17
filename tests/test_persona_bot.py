import unittest
import sys

# Setup environment to avoid dependency issues with aiogram / aiohttp / openai
class MockAiohttp:
    class SocketTimeoutError(Exception): pass
    class ClientError(Exception): pass
sys.modules['aiohttp'] = MockAiohttp()
sys.modules['aiohttp.SocketTimeoutError'] = MockAiohttp.SocketTimeoutError

from site_tgach.persona_bot import is_valid_for_persona

class TestIsValidForPersona(unittest.TestCase):
    def test_valid_strings(self):
        """Test strings that should be valid"""
        self.assertTrue(is_valid_for_persona("Hello world"))
        self.assertTrue(is_valid_for_persona("a"))
        self.assertTrue(is_valid_for_persona("  padded  "))

    def test_empty_strings(self):
        """Test empty or None strings"""
        self.assertFalse(is_valid_for_persona(""))
        self.assertFalse(is_valid_for_persona(None)) # type: ignore
        self.assertFalse(is_valid_for_persona("   "))

    def test_commands(self):
        """Test command strings"""
        self.assertFalse(is_valid_for_persona("/start"))
        self.assertFalse(is_valid_for_persona(" /help"))

    def test_short_non_alpha(self):
        """Test short non-alphabetical strings"""
        self.assertFalse(is_valid_for_persona("1"))
        self.assertFalse(is_valid_for_persona("!"))
        self.assertFalse(is_valid_for_persona(" . "))
        self.assertTrue(is_valid_for_persona("12"))

if __name__ == '__main__':
    unittest.main()
