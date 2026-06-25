import unittest
import os
import sys

# Add project root to sys.path to allow importing from common
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from common.html_utils import escape_html

class TestHtmlUtils(unittest.TestCase):
    def test_escape_html_empty_or_none(self):
        self.assertEqual(escape_html(""), "")
        self.assertEqual(escape_html(None), None)

    def test_escape_html_no_special_chars(self):
        self.assertEqual(escape_html("Hello World"), "Hello World")
        self.assertEqual(escape_html("12345"), "12345")
        self.assertEqual(escape_html("Safe_text-123"), "Safe_text-123")

    def test_escape_html_ampersand(self):
        self.assertEqual(escape_html("H&M"), "H&amp;M")
        self.assertEqual(escape_html("&"), "&amp;")
        self.assertEqual(escape_html("&&"), "&amp;&amp;")

    def test_escape_html_brackets(self):
        self.assertEqual(escape_html("<script>"), "&lt;script&gt;")
        self.assertEqual(escape_html("A < B > C"), "A &lt; B &gt; C")
        self.assertEqual(escape_html("<>"), "&lt;&gt;")

    def test_escape_html_quotes(self):
        self.assertEqual(escape_html('"Hello"'), "&quot;Hello&quot;")
        self.assertEqual(escape_html('a"b'), "a&quot;b")
        self.assertEqual(escape_html('""'), "&quot;&quot;")

    def test_escape_html_combined(self):
        self.assertEqual(
            escape_html('<a href="https://example.com/a&b">Link</a>'),
            "&lt;a href=&quot;https://example.com/a&amp;b&quot;&gt;Link&lt;/a&gt;"
        )
        self.assertEqual(
            escape_html('Tom & Jerry said "Hello <World>"'),
            "Tom &amp; Jerry said &quot;Hello &lt;World&gt;&quot;"
        )

if __name__ == '__main__':
    unittest.main()
