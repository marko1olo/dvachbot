import os
import sys
import unittest
import html
import re

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from site_tgach.main import format_post_text as format_post_text_site, _clean_url_and_suffix as clean_site
from Dubsite_tgach.main import format_post_text as format_post_text_dubsite, _clean_url_and_suffix as clean_dub

class TestChallengerM1DeepStress(unittest.TestCase):

    def test_01_multi_query_params_and_anchors(self):
        """Test complex multi-query params and # anchors in Python"""
        test_cases = [
            "https://example.com/search?q=1&b=2&c=3&d=4#fragment",
            "https://youtube.com/watch?v=dQw4w9WgXcQ&t=30s&list=PL123#t=10s",
            "https://example.com/api?param1=val1&param2=val2&param3=val3",
            "https://example.com/page?id=50&ref=abc#section-2"
        ]
        for url in test_cases:
            res_site = format_post_text_site(f"Link: {url}")
            res_dub = format_post_text_dubsite(f"Link: {url}")

            # HTML escaped expected URL
            escaped_url = html.escape(url)
            
            # Check site_tgach
            self.assertIn(f'href="{escaped_url}"', res_site, f"Site href mismatch for {url}: {res_site}")
            # Check Dubsite_tgach
            self.assertIn(f'href="{escaped_url}"', res_dub, f"Dubsite href mismatch for {url}: {res_dub}")

    def test_02_corrupted_trailing_quotes_entities_and_text(self):
        """Test corrupted URL trailing quotes, HTML entities, and Cyrillic text"""
        test_cases = [
            (">>1234 https://domain.com/b/res/343717.html'>ТГАЧ", "https://domain.com/b/res/343717.html", "&gt;ТГАЧ"),
            ('>>1234 https://domain.com/b/res/343717.html">ТГАЧ', "https://domain.com/b/res/343717.html", "&quot;&gt;ТГАЧ"),
            (">>1234 https://domain.com/path?a=1&b=2&#039;&gt;ТГАЧ", "https://domain.com/path?a=1&amp;b=2", "&gt;ТГАЧ"),
            (">>1234 https://domain.com/path?a=1&b=2&#x27;&gt;ТГАЧ", "https://domain.com/path?a=1&amp;b=2", "&gt;ТГАЧ"),
            (">>1234 https://domain.com/path?a=1&b=2&quot;&gt;ТГАЧ", "https://domain.com/path?a=1&amp;b=2", "&quot;&gt;ТГАЧ"),
        ]
        for raw, expected_href, expected_suffix_end in test_cases:
            res_site = format_post_text_site(raw)
            res_dub = format_post_text_dubsite(raw)

            # Assert clean href
            self.assertIn(f'href="{expected_href}"', res_site, f"Site failed clean href for {raw}: {res_site}")
            self.assertIn(f'href="{expected_href}"', res_dub, f"Dubsite failed clean href for {raw}: {res_dub}")

            # Assert href does not contain trailing entity / quote leakage
            href_match = re.search(r'href="(https://[^"]+)"', res_site)
            self.assertIsNotNone(href_match)
            self.assertEqual(href_match.group(1), expected_href, f"Leaked characters in href: {href_match.group(1)}")

            # Assert suffix comes after </a> and ends with expected suffix
            self.assertTrue(res_site.endswith(expected_suffix_end), f"Suffix misplaced in site: {res_site}")

    def test_03_balanced_and_unbalanced_parentheses(self):
        """Test URL with balanced parens (Wikipedia) vs trailing paren in sentence"""
        # Wikipedia balanced paren
        wiki_url = "https://en.wikipedia.org/wiki/Python_(programming_language)"
        res_wiki = format_post_text_site(f"Check {wiki_url}")
        self.assertIn(f'href="{wiki_url}"', res_wiki)

        # Sentence with trailing paren
        sentence_url = "https://example.com/test"
        res_sent = format_post_text_site(f"(Check {sentence_url})")
        self.assertIn(f'href="{sentence_url}"', res_sent)
        self.assertIn(f'</a>)', res_sent)

    def test_04_trailing_sentence_punctuation(self):
        """Test URL ending with period, comma, exclamation, question mark"""
        base = "https://example.com/page"
        for punct in [".", ",", "!", "?"]:
            raw = f"Visit {base}{punct}"
            res = format_post_text_site(raw)
            self.assertIn(f'href="{base}"', res)
            self.assertIn(f'</a>{punct}', res)

if __name__ == "__main__":
    unittest.main()
