from __future__ import annotations

import unittest
from common.html_utils import escape_html

class EscapeHtmlTests(unittest.TestCase):
    def test_escape_html_basic(self):
        self.assertEqual(escape_html("Hello <world> & \"friends\""), "Hello &lt;world&gt; &amp; &quot;friends&quot;")

    def test_escape_html_empty_string(self):
        self.assertEqual(escape_html(""), "")

    def test_escape_html_none(self):
        self.assertIsNone(escape_html(None))

    def test_escape_html_no_special_chars(self):
        self.assertEqual(escape_html("Just a normal string."), "Just a normal string.")

    def test_escape_html_multiple_replacements(self):
        self.assertEqual(escape_html("<<>>&&\"\""), "&lt;&lt;&gt;&gt;&amp;&amp;&quot;&quot;")

if __name__ == "__main__":
    unittest.main()
