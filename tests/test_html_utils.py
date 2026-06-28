import unittest
from common.html_utils import clean_html_tags

class TestCleanHtmlTags(unittest.TestCase):
    def test_none_input(self):
        self.assertEqual(clean_html_tags(None), "")

    def test_empty_string(self):
        self.assertEqual(clean_html_tags(""), "")

    def test_no_tags(self):
        text = "Just a regular text without tags."
        self.assertEqual(clean_html_tags(text), text)

    def test_simple_tags(self):
        self.assertEqual(clean_html_tags("<b>Bold text</b>"), "Bold text")
        self.assertEqual(clean_html_tags("<p>Paragraph</p>"), "Paragraph")

    def test_nested_tags(self):
        self.assertEqual(clean_html_tags("<div><p><b>Nested</b> text</p></div>"), "Nested text")

    def test_tags_with_attributes(self):
        self.assertEqual(clean_html_tags('<a href="https://example.com">Link</a>'), "Link")
        self.assertEqual(clean_html_tags('<img src="image.jpg" alt="Description" /> Image'), " Image")

    def test_malformed_tags(self):
        self.assertEqual(clean_html_tags("Text with < unfinished tag"), "Text with < unfinished tag")
        self.assertEqual(clean_html_tags("Text with > unmatched bracket"), "Text with > unmatched bracket")

if __name__ == '__main__':
    unittest.main()
