import sys
import os
import types
import unittest
import importlib.util
from unittest.mock import patch

import json as std_json

class TestMainUjsonFallback(unittest.TestCase):
    def load_main_module(self):
        """Helper to load main.py and catch any initialization exceptions."""
        spec = importlib.util.spec_from_file_location("main_test_fallback", "main.py")
        main_mod = importlib.util.module_from_spec(spec)
        try:
            # We execute the module. It might fail on later imports/logic,
            # but we only care about the top-level json assignment.
            spec.loader.exec_module(main_mod)
        except Exception:
            pass
        return main_mod

    @patch.dict('sys.modules', {'ujson': None})
    def test_ujson_missing_fallback(self):
        """Test that main.py falls back to standard json if ujson is missing."""
        main_mod = self.load_main_module()

        self.assertIs(
            getattr(main_mod, 'json', None),
            std_json,
            "main.json should be standard json when ujson is missing"
        )

    def test_ujson_present(self):
        """Test that main.py uses ujson if it is available."""
        dummy_ujson = types.ModuleType('ujson')
        dummy_ujson.__name__ = 'ujson'

        with patch.dict('sys.modules', {'ujson': dummy_ujson}):
            main_mod = self.load_main_module()

        self.assertIs(
            getattr(main_mod, 'json', None),
            dummy_ujson,
            "main.json should be ujson when it is available"
        )

if __name__ == '__main__':
    unittest.main()
