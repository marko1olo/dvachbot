import os
import sys
import unittest
import html
import re

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from site_tgach.main import format_post_text as format_post_text_site
from Dubsite_tgach.main import format_post_text as format_post_text_dubsite
from common.text_utils import sanitize_html


class TestHtmlAnchorsBackend(unittest.TestCase):
    def test_site_tgach_format_post_text_corrupted_link(self):
        raw_text = ">>1234 https://domain.com/b/res/343717.html'>ТГАЧ"
        result = format_post_text_site(raw_text)

        # Check href attribute in result
        href_match = re.search(r'href="([^"]+)"', result)
        self.assertIsNotNone(href_match, f"No href attribute found in: {result}")
        href_val = href_match.group(1)

        # Href for the URL should be strictly clean
        url_href_match = re.search(r'<a href="([^"]+)" [^>]*rel="noopener noreferrer"', result)
        self.assertIsNotNone(url_href_match, f"No auto-link href found in: {result}")
        url_href = url_href_match.group(1)

        self.assertEqual(url_href, "https://domain.com/b/res/343717.html")
        self.assertNotIn("&#039;", url_href)
        self.assertNotIn("&#x27;", url_href)
        self.assertNotIn("&gt;", url_href)
        self.assertNotIn("ТГАЧ", url_href)
        self.assertNotIn("'", url_href)

        # Ensure no nested <a> tags
        nested_a = re.search(r'<a\b[^>]*>\s*<a\b', result)
        self.assertIsNone(nested_a, f"Nested <a> tags found in: {result}")

    def test_dubsite_tgach_format_post_text_corrupted_link(self):
        raw_text = ">>1234 https://domain.com/b/res/343717.html'>ТГАЧ"
        result = format_post_text_dubsite(raw_text)

        url_href_match = re.search(r'<a href="([^"]+)" [^>]*rel="noopener noreferrer"', result)
        self.assertIsNotNone(url_href_match, f"No auto-link href found in: {result}")
        url_href = url_href_match.group(1)

        self.assertEqual(url_href, "https://domain.com/b/res/343717.html")
        self.assertNotIn("&#039;", url_href)
        self.assertNotIn("&#x27;", url_href)
        self.assertNotIn("&gt;", url_href)
        self.assertNotIn("ТГАЧ", url_href)
        self.assertNotIn("'", url_href)

    def test_post_reference_links(self):
        raw_text = ">>1234 Check post >>5678 and cross >>/b/999"
        res_site = format_post_text_site(raw_text)
        res_dub = format_post_text_dubsite(raw_text)

        self.assertIn('href="#post-1234"', res_site)
        self.assertIn('href="#post-5678"', res_site)
        self.assertIn('href="/b/res/0#post-999"', res_site)

        self.assertIn('href="#post-1234"', res_dub)
        self.assertIn('href="#post-5678"', res_dub)
        self.assertIn('href="/b/res/0#post-999"', res_dub)

    def test_sanitize_html_quotes_and_attributes(self):
        text = '<a href="https://example.com/test\'quote">Link</a>'
        sanitized = sanitize_html(text)
        self.assertIn('href="https://example.com/test&#x27;quote"', sanitized)

    def test_multi_parameter_url_preservation(self):
        # 1. Multi-parameter search URL
        search_text = "Check https://example.com/search?q=1&lang=en"
        site_search = format_post_text_site(search_text)
        dub_search = format_post_text_dubsite(search_text)

        for res in (site_search, dub_search):
            url_match = re.search(r'<a href="([^"]+)"', res)
            self.assertIsNotNone(url_match, f"No href found in: {res}")
            href = url_match.group(1)
            self.assertIn("q=1", href, f"Parameter q=1 truncated in: {href}")
            self.assertTrue("lang=en" in href or "&amp;lang=en" in href, f"Parameter lang=en truncated in: {href}")

        # 2. YouTube timestamp link
        yt_text = "Watch https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=30s"
        site_yt = format_post_text_site(yt_text)
        dub_yt = format_post_text_dubsite(yt_text)

        for res in (site_yt, dub_yt):
            url_match = re.search(r'<a href="([^"]+)"', res)
            self.assertIsNotNone(url_match, f"No href found in: {res}")
            href = url_match.group(1)
            self.assertIn("v=dQw4w9WgXcQ", href, f"Parameter v missing in: {href}")
            self.assertTrue("t=30s" in href or "&amp;t=30s" in href, f"Parameter t missing in: {href}")

        # 3. Multi-parameter URL with trailing corrupted quotes & Russian text
        corrupted_multi = ">>1234 https://example.com/search?q=foo&category=all'>Текст"
        site_corr = format_post_text_site(corrupted_multi)
        dub_corr = format_post_text_dubsite(corrupted_multi)

        for res in (site_corr, dub_corr):
            url_match = re.search(r'<a href="([^"]+)" [^>]*rel="noopener noreferrer"', res)
            self.assertIsNotNone(url_match, f"No auto-link href found in: {res}")
            href = url_match.group(1)
            self.assertIn("q=foo", href)
            self.assertTrue("category=all" in href or "&amp;category=all" in href)
            self.assertNotIn("&#039;", href)
            self.assertNotIn("&#x27;", href)
            self.assertNotIn("&gt;", href)
            self.assertNotIn("Текст", href)


if __name__ == "__main__":
    unittest.main()

