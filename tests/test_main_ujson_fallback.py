import types
import unittest
from unittest.mock import patch

import json as std_json

class TestMainUjsonFallback(unittest.TestCase):
    def load_main_module(self):
        """Helper to test json import logic from main.py without full bot side effects."""
        with open("main.py", "r", encoding="utf-8") as f:
            code_lines = []
            for line in f:
                code_lines.append(line)
                if "import logging" in line:
                    break
            code = "".join(code_lines)

        namespace = {"__name__": "main"}
        exec(code, namespace)
        return types.SimpleNamespace(**namespace)

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

