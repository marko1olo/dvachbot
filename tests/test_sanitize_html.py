import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from common.text_utils import sanitize_html

class TestSanitizeHtml(unittest.TestCase):
    def test_empty_string(self):
        """Test that empty string and None return empty string."""
        self.assertEqual(sanitize_html(""), "")
        self.assertEqual(sanitize_html(None), "")

    def test_no_links(self):
        """Test that regular text and safe HTML without links is preserved."""
        self.assertEqual(sanitize_html("Just some text"), "Just some text")
        self.assertEqual(sanitize_html("Text with <b>bold</b>"), "Text with <b>bold</b>")

    def test_https_www_link(self):
        """Test standard https://www. link replacement."""
        self.assertEqual(
            sanitize_html('hello <a href="https://www.example.com">my link</a> world'),
            'hello <a href="https://www.example.com">my link</a> world'
        )

    def test_http_link(self):
        """Test standard http:// link replacement."""
        self.assertEqual(
            sanitize_html('hello <a href="http://example.com">my link</a> world'),
            'hello <a href="http://example.com">my link</a> world'
        )

    def test_no_protocol_link(self):
        """Test link without explicit protocol."""
        self.assertEqual(
            sanitize_html('hello <a href="example.com">my link</a> world'),
            'hello my link world'
        )

    def test_link_with_path_and_query(self):
        """Test link with path and query arguments."""
        self.assertEqual(
            sanitize_html('hello <a href="https://example.com/page?test=1">my link</a> world'),
            'hello <a href="https://example.com/page?test=1">my link</a> world'
        )

    def test_link_with_single_quotes(self):
        """Test links formatted with single quotes."""
        self.assertEqual(
            sanitize_html("hello <a href='https://example.com'>my link</a> world"),
            'hello <a href="https://example.com">my link</a> world'
        )

    def test_multiple_links(self):
        """Test multiple link replacements in one text block."""
        self.assertEqual(
            sanitize_html('Visit <a href="https://site1.com">site one</a> and <a href="http://www.site2.org/path">site two</a>!'),
            'Visit <a href="https://site1.com">site one</a> and <a href="http://www.site2.org/path">site two</a>!'
        )

    def test_link_with_attributes(self):
        """Test links containing additional HTML attributes."""
        self.assertEqual(
            sanitize_html('<a class="test" href="https://example.com" target="_blank">link</a>'),
            '<a href="https://example.com">link</a>'
        )

    def test_dangerous_tags_removal(self):
        """Test that dangerous tags are removed properly."""
        # script tag removal
        self.assertEqual(
            sanitize_html('<script>alert("XSS")</script>Hello'),
            'Hello'
        )

        # iframe and object removal
        self.assertEqual(
            sanitize_html('Check this <iframe src="bad"></iframe> out'),
            'Check this  out'
        )

        self.assertEqual(
            sanitize_html('<object data="flash.swf"></object>Test'),
            'Test'
        )

    def test_telegram_link_preserved(self):
        """Test that Telegram and Telegraph links are preserved as actual HTML links."""
        self.assertEqual(
            sanitize_html('Check <a href="https://t.me/zakat_2">Gentleman</a> channel'),
            'Check <a href="https://t.me/zakat_2">Gentleman</a> channel'
        )
        self.assertEqual(
            sanitize_html('Read <a href="http://telegra.ph/some-article">article</a> now'),
            'Read <a href="http://telegra.ph/some-article">article</a> now'
        )

if __name__ == '__main__':
    unittest.main()
