import os
import sys
import unittest
from pathlib import Path
import asyncio

# Setup env variables before importing main
os.environ["SECRET_KEY"] = "test"
os.environ["BOT_TOKEN"] = "test"
os.environ["OPENAI_API_KEY"] = "test"
os.environ['ADMIN_CHAT_ID'] = '123456789'
os.environ['API_ID'] = '123'
os.environ['API_HASH'] = 'test_hash'
os.environ['BASE_URL'] = 'http://test.com'

# Setup asyncio loop for Pyrogram imports
try:
    asyncio.get_running_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Now import the module
from Dubsite_tgach.main import sanitize_html

class TestSanitizeHtml(unittest.TestCase):
    def test_empty_string(self):
        """Test that an empty string or None returns an empty string."""
        self.assertEqual(sanitize_html(""), "")
        self.assertEqual(sanitize_html(None), "")

    def test_normal_text(self):
        """Test that normal text without HTML is returned unchanged."""
        text = "Hello, World!"
        self.assertEqual(sanitize_html(text), text)

    def test_html_tags(self):
        """Test that HTML tags are properly escaped."""
        text = "<b>bold</b> <script>alert(1);</script>"
        expected = "&lt;b&gt;bold&lt;/b&gt; &lt;script&gt;alert(1);&lt;/script&gt;"
        self.assertEqual(sanitize_html(text), expected)

    def test_quotes_preserved(self):
        """Test that quotes are preserved as quote=False is used."""
        text = 'He said "Hello" and \'World\''
        self.assertEqual(sanitize_html(text), text)

    def test_mixed_html_and_quotes(self):
        """Test mixed HTML and quotes."""
        text = '<a href="http://example.com">Link</a>'
        expected = '&lt;a href="http://example.com"&gt;Link&lt;/a&gt;'
        self.assertEqual(sanitize_html(text), expected)

if __name__ == '__main__':
    unittest.main()
