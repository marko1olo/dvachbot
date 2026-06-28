import unittest
from common.html_utils import clean_html_tags, escape_html

class TestHtmlUtils(unittest.TestCase):
    def test_clean_html_tags_empty_string(self):
        """Test that an empty string returns an empty string."""
        self.assertEqual(clean_html_tags(""), "")

    def test_clean_html_tags_none_input(self):
        """Test that None returns None."""
        self.assertEqual(clean_html_tags(None), None)

    def test_clean_html_tags_no_tags(self):
        """Test that normal text is returned unchanged."""
        text = "Hello, World!"
        self.assertEqual(clean_html_tags(text), text)

    def test_clean_html_tags_basic_tags(self):
        """Test simple HTML tags removal."""
        text = "<b>Bold</b> and <i>italic</i>"
        self.assertEqual(clean_html_tags(text), "Bold and italic")

    def test_clean_html_tags_nested_tags(self):
        """Test nested HTML tags removal."""
        text = "<div><p>Paragraph with <span>span</span></p></div>"
        self.assertEqual(clean_html_tags(text), "Paragraph with span")

    def test_clean_html_tags_tags_with_attributes(self):
        """Test HTML tags with attributes removal."""
        text = '<a href="https://example.com" class="link">Link</a>'
        self.assertEqual(clean_html_tags(text), "Link")

    def test_clean_html_tags_unclosed_tags(self):
        """Test unclosed tag matching according to the regex pattern."""
        text = "This is <br text"
        self.assertEqual(clean_html_tags(text), text)

    def test_clean_html_tags_multiline_text(self):
        """Test HTML removal across multiple lines."""
        text = "<p>Line 1</p>\n<p>Line 2</p>"
        self.assertEqual(clean_html_tags(text), "Line 1\nLine 2")

    def test_clean_html_tags_script_and_style(self):
        """Test script and style tags (note: it removes tags, but leaves content)."""
        text = "<script>alert(1);</script><style>.cls { color: red; }</style>"
        self.assertEqual(clean_html_tags(text), "alert(1);.cls { color: red; }")

if __name__ == '__main__':
    unittest.main()
