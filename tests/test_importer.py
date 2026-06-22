import unittest
import asyncio
from unittest.mock import patch, MagicMock
import os
import sys

# Add project root to sys.path to allow importing from Dubsite_tgach
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock environment variables needed for initialization
os.environ["SECRET_KEY"] = "dummy_secret_key"
os.environ["BOT_TOKEN"] = "dummy_bot_token"
os.environ["OPENAI_API_KEY"] = "dummy_openai_key"


class TestImporter(unittest.TestCase):
    def setUp(self):
        # We need an event loop for Pyrogram to import
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    def test_normalize_html_sync_unescape(self):
        from Dubsite_tgach.importer import ThreadImporter
        importer_instance = ThreadImporter(bot=None, file_storage_channel_id=123)

        # Test basic escaped HTML
        raw_html = "Hello &lt;br&gt; World"
        normalized = importer_instance._normalize_html_sync(raw_html)

        # In the original method, <br> is replaced with \n and extra spaces might be present
        self.assertEqual(normalized, "Hello \n World")

        # Test other escaped entities
        raw_html = "&quot;Hello&quot; &amp; &#39;World&#39;"
        normalized = importer_instance._normalize_html_sync(raw_html)
        self.assertEqual(normalized, "\"Hello\" & 'World'")

        # Test that unescaped tags are processed correctly
        # (BeautifulSoup strips scripts and some tags, unwraps others)
        raw_html = "&lt;script&gt;alert(1)&lt;/script&gt;Hello"
        normalized = importer_instance._normalize_html_sync(raw_html)
        # script should be stripped
        self.assertEqual(normalized, "Hello")

        # Test spoiler
        raw_html = "Text &lt;span class=&quot;spoiler&quot;&gt;hidden&lt;/span&gt;"
        normalized = importer_instance._normalize_html_sync(raw_html)
        self.assertEqual(normalized, "Text ||hidden||")


    def test_normalize_html_sync_site_tgach(self):
        from site_tgach.importer import ThreadImporter
        importer_instance = ThreadImporter(bot=None, file_storage_channel_id=123)

        # Test empty string
        self.assertEqual(importer_instance._normalize_html_sync(""), "")

        # Test forum-specific string replacements
        test_strings = {
            "Двач": "тгач",
            "харкач": "тгач",
            "сосач": "тгач",
            "двачер": "тгачер",
            "Двощ": "тгач",
            "абу": "админ",
            "mailru": "tganon",
            "2ch": "tgach",
            "2chan": "tgachan", # 2ch -> tgach, an -> an -> tgachan
            "4chan": "tgach"
        }
        for original, expected in test_strings.items():
            self.assertEqual(importer_instance._normalize_html_sync(original), expected)

        # Test removal of unwanted tags (using html.parser fallback because lxml parses <wbr>Hello as <wbr>Hello</wbr> and drops it)
        # We test tags that won't wrap trailing text in lxml.
        raw_html = "<script>alert(1)</script><style>body { color: red; }</style><iframe></iframe><object></object><embed></embed><applet></applet><form></form><button>Click</button><meta name='description'><link rel='stylesheet'><img src='test.jpg'>Hello"
        self.assertEqual(importer_instance._normalize_html_sync(raw_html), "Hello")

        # Test <br> replacement
        raw_html = "Hello<br>World<br/>!"
        self.assertEqual(importer_instance._normalize_html_sync(raw_html), "Hello\nWorld\n!")

        # Test <p> and <div> unwrapping and \n insertion
        raw_html = "<p>Paragraph 1</p><div>Div 1</div>"
        self.assertEqual(importer_instance._normalize_html_sync(raw_html), "Paragraph 1\nDiv 1")

        # Test spoiler format conversion
        raw_html = "This is a <span class=\"spoiler\">secret</span> message."
        self.assertEqual(importer_instance._normalize_html_sync(raw_html), "This is a ||secret|| message.")

        # Test link replacing with href text
        raw_html = "<a href='https://example.com'>link text</a>"
        self.assertEqual(importer_instance._normalize_html_sync(raw_html), "link text")

        # Test (OP) stripping
        raw_html = "User (OP)"
        self.assertEqual(importer_instance._normalize_html_sync(raw_html), "User")

        # Test multiple space collapsing
        raw_html = "Too    many     spaces"
        self.assertEqual(importer_instance._normalize_html_sync(raw_html), "Too many spaces")

        # Test multiple newline collapsing
        raw_html = "Line 1\n\n\n\nLine 2"
        self.assertEqual(importer_instance._normalize_html_sync(raw_html), "Line 1\n\nLine 2")

    def test_normalize_html_sync_ast_unescape(self):
        import inspect
        import ast
        import textwrap
        from Dubsite_tgach.importer import ThreadImporter

        source = inspect.getsource(ThreadImporter._normalize_html_sync)
        source = textwrap.dedent(source)
        tree = ast.parse(source)

        unescape_found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr == 'unescape':
                        unescape_found = True
                        break

        self.assertTrue(unescape_found, "unescape must be called in _normalize_html_sync to allow BeautifulSoup to parse tags properly")

if __name__ == "__main__":
    unittest.main()
