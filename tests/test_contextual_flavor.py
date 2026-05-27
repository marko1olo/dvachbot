from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import contextual_flavor as cf


class ContextualFlavorTests(unittest.TestCase):
    def test_cyrillic_patterns_match_real_utf8_text(self) -> None:
        samples = [
            "\u0434\u0435\u0434\u043b\u043e\u043a",
            "\u0441\u0430\u0439\u0442",
            "\u0432\u0430\u0439\u0431",
            "\u043a\u043e\u0434\u0438\u0440\u043e\u0432\u043a\u0430",
        ]

        for text in samples:
            with self.subTest(text=text):
                self.assertTrue(
                    any(pattern.search(text) for pattern, _ in cf.CONTEXTUAL_REPLY_EXTENSIONS_RU),
                    text,
                )

    def test_installer_preserves_existing_rules_after_extensions(self) -> None:
        existing_pattern = re.compile(r"\bexisting-only\b", re.IGNORECASE)
        target = {existing_pattern: ["existing reply"]}

        cf.install_contextual_reply_extensions(target)

        keys = list(target)
        self.assertIn(existing_pattern, target)
        self.assertGreater(len(keys), 1)
        self.assertIs(keys[-1], existing_pattern)

    def test_reply_groups_are_non_empty(self) -> None:
        for pattern, replies in cf.CONTEXTUAL_REPLY_EXTENSIONS_RU:
            with self.subTest(pattern=pattern.pattern):
                self.assertGreater(len(replies), 0)
                self.assertTrue(all(isinstance(reply, str) and reply for reply in replies))


if __name__ == "__main__":
    unittest.main()
