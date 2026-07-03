import os
import sys
import unittest
from pathlib import Path
import asyncio

# Setup env variables before importing main to prevent side effects
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
from main import convert_site_tags_to_telegram

class TestConvertSiteTagsToTelegram(unittest.TestCase):
    def test_empty_string(self):
        self.assertEqual(convert_site_tags_to_telegram(""), "")
        self.assertEqual(convert_site_tags_to_telegram(None), "")

    def test_plain_text(self):
        text = "Hello world! This is a simple test without any tags."
        self.assertEqual(convert_site_tags_to_telegram(text), text)

    def test_basic_tags(self):
        self.assertEqual(convert_site_tags_to_telegram("[b]bold[/b]"), "<b>bold</b>")
        self.assertEqual(convert_site_tags_to_telegram("[i]italic[/i]"), "<i>italic</i>")
        self.assertEqual(convert_site_tags_to_telegram("[u]underline[/u]"), "<u>underline</u>")
        self.assertEqual(convert_site_tags_to_telegram("[s]strikethrough[/s]"), "<s>strikethrough</s>")
        self.assertEqual(convert_site_tags_to_telegram("||hidden||"), "<tg-spoiler>hidden</tg-spoiler>")
        self.assertEqual(convert_site_tags_to_telegram("[blur]hidden[/blur]"), "<tg-spoiler>hidden</tg-spoiler>")
        self.assertEqual(convert_site_tags_to_telegram("[shake]hidden[/shake]"), "<i>hidden</i>")
        self.assertEqual(convert_site_tags_to_telegram("[rainbow]hidden[/rainbow]"), "<code>hidden</code>")
        self.assertEqual(convert_site_tags_to_telegram("[glitch]hidden[/glitch]"), "<s><code>hidden</code></s>")
        self.assertEqual(convert_site_tags_to_telegram("[code]print('hello')[/code]"), "<code>print('hello')</code>")

    def test_multiple_tags(self):
        text = "This is [b]bold[/b] and this is [i]italic[/i] text."
        expected = "This is <b>bold</b> and this is <i>italic</i> text."
        self.assertEqual(convert_site_tags_to_telegram(text), expected)

    def test_nested_tags(self):
        text = "[b]Bold and [i]italic[/i][/b]"
        expected = "<b>Bold and <i>italic</i></b>"
        self.assertEqual(convert_site_tags_to_telegram(text), expected)

    def test_re_dotall(self):
        # Ensure newlines inside tags are handled correctly
        text = "[code]line 1\nline 2[/code]"
        expected = "<code>line 1\nline 2</code>"
        self.assertEqual(convert_site_tags_to_telegram(text), expected)

    def test_mismatched_tags(self):
        # Tags that are opened but not closed
        text = "[b]this is bold without closing tag"
        self.assertEqual(convert_site_tags_to_telegram(text), text)

        # Tags that are closed but not opened
        text = "this is bold without opening tag[/b]"
        self.assertEqual(convert_site_tags_to_telegram(text), text)

    def test_nested_same_tags(self):
        text = "[b]outer [b]inner[/b][/b]"
        # First `[b]` matches up to first `[/b]`: <b>outer [b]inner</b>[/b]
        expected = "<b>outer [b]inner</b>[/b]"
        self.assertEqual(convert_site_tags_to_telegram(text), expected)


if __name__ == '__main__':
    unittest.main()
