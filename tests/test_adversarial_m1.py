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

class TestAdversarialBackend(unittest.TestCase):
    def test_query_params(self):
        raw_text = "Check this url: https://example.com/page?a=1&b=2"
        res = format_post_text_site(raw_text)
        print("RESULT FOR QUERY PARAMS:")
        print(res)

if __name__ == "__main__":
    unittest.main()
