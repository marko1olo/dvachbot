import unittest
import os
import asyncio

# Mock environment variables before importing
os.environ['SECRET_KEY'] = 'test_secret_key'
os.environ['BOT_TOKEN'] = 'test_bot_token'
os.environ['OPENAI_API_KEY'] = 'test_openai_api_key'

# Create and set new event loop to avoid Pyrogram/asyncio errors
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from Dubsite_tgach.main import sanitize_html

class TestSanitizeHtml(unittest.TestCase):
    def test_empty_string(self):
        self.assertEqual(sanitize_html(""), "")

    def test_none(self):
        self.assertEqual(sanitize_html(None), "")

    def test_html_tags(self):
        self.assertEqual(
            sanitize_html("<script>alert('xss')</script>"),
            "&lt;script&gt;alert('xss')&lt;/script&gt;"
        )
        self.assertEqual(
            sanitize_html("A & B"),
            "A &amp; B"
        )

    def test_quotes(self):
        # With quote=False, quotes should remain unescaped
        self.assertEqual(
            sanitize_html('<div class="test" id=\'a\'>'),
            '&lt;div class="test" id=\'a\'&gt;'
        )
        self.assertEqual(
            sanitize_html("\"quotes'"),
            "\"quotes'"
        )

if __name__ == '__main__':
    unittest.main()
