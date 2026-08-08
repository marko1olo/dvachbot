import os
import sys
import unittest
import html
import re

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from site_tgach.main import format_post_text as format_post_text_site
from Dubsite_tgach.main import format_post_text as format_post_text_dubsite
from common.text_utils import sanitize_html

class TestAdversarialSuiteM1Backend(unittest.TestCase):

    def test_01_multi_query_params_truncated(self):
        """CRITICAL REGRESSION: URLs with & query parameters get truncated at &"""
        raw_text = "Check URL: https://example.com/search?q=cat&lang=ru&page=2"
        res_site = format_post_text_site(raw_text)
        res_dub = format_post_text_dubsite(raw_text)

        # Expected full URL in href: https://example.com/search?q=cat&amp;lang=ru&amp;page=2
        # Or at least containing lang=ru and page=2 in the href attribute
        self.assertIn('lang=ru', res_site, f"Query param lang=ru missing from link in site_tgach: {res_site}")
        self.assertIn('href="https://example.com/search?q=cat&amp;lang=ru&amp;page=2"', res_site, f"Truncated URL in site_tgach href: {res_site}")

        self.assertIn('lang=ru', res_dub, f"Query param lang=ru missing from link in Dubsite_tgach: {res_dub}")

    def test_02_fragment_anchors_truncated(self):
        """CRITICAL REGRESSION: URLs with # fragment anchors get truncated at #"""
        raw_text = "Documentation: https://example.com/docs.html#section-install"
        res_site = format_post_text_site(raw_text)
        
        self.assertIn('href="https://example.com/docs.html#section-install"', res_site, f"Truncated URL in href: {res_site}")

    def test_03_original_bug_corrupted_link(self):
        """Test original bug case: >>1234 https://domain.com/b/res/343717.html'>ТГАЧ"""
        raw_text = ">>1234 https://domain.com/b/res/343717.html'>ТГАЧ"
        res_site = format_post_text_site(raw_text)

        # Check href attribute in result
        url_href_match = re.search(r'<a href="([^"]+)" [^>]*rel="noopener noreferrer"', res_site)
        self.assertIsNotNone(url_href_match, f"No auto-link href found in: {res_site}")
        url_href = url_href_match.group(1)

        self.assertEqual(url_href, "https://domain.com/b/res/343717.html")
        self.assertNotIn("&#039;", url_href)
        self.assertNotIn("&gt;", url_href)
        self.assertNotIn("ТГАЧ", url_href)

    def test_04_double_quote_and_cyrillic(self):
        """Test URL followed by double quote and Cyrillic: https://domain.com/path">Текст"""
        raw_text = '>>1234 https://domain.com/path">Текст'
        res = format_post_text_site(raw_text)
        url_href_match = re.search(r'<a href="([^"]+)" [^>]*rel="noopener noreferrer"', res)
        self.assertIsNotNone(url_href_match, f"No auto-link href found in: {res}")
        url_href = url_href_match.group(1)
        self.assertEqual(url_href, "https://domain.com/path")

    def test_05_no_nested_anchors(self):
        """Verify no nested <a> tags are produced"""
        raw_text = ">>1234 https://example.com/test"
        res = format_post_text_site(raw_text)
        nested = re.search(r'<a\b[^>]*>\s*<a\b', res)
        self.assertIsNone(nested, f"Nested <a> tags detected: {res}")

if __name__ == "__main__":
    unittest.main()
