# -*- coding: utf-8 -*-
"""
test_banner_manager.py — Unit Tests for Banner Manager & Category Associations
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import banner_manager
from banner_manager import (
    get_banner_file,
    get_all_banners_summary,
    CATEGORY_PATTERNS,
    _CATEGORIZED_BANNERS,
    BANNERS_DIR
)


class TestBannerManager(unittest.TestCase):

    def test_all_banners_exist_and_count(self):
        summary = get_all_banners_summary()
        self.assertEqual(summary["total_banners"], 383)
        self.assertGreaterEqual(summary["cached_file_ids"], 0)

    def test_category_expansion_thresholds(self):
        cats = _CATEGORIZED_BANNERS
        self.assertEqual(len(cats["start"]), 383)
        self.assertEqual(len(cats["all"]), 383)

        # Requirements: shop >= 100, wallet >= 120, roulette >= 120
        self.assertGreaterEqual(len(cats["shop"]), 100, f"Shop category must have >= 100 banners, got {len(cats['shop'])}")
        self.assertGreaterEqual(len(cats["wallet"]), 120, f"Wallet category must have >= 120 banners, got {len(cats['wallet'])}")
        self.assertGreaterEqual(len(cats["roulette"]), 120, f"Roulette category must have >= 120 banners, got {len(cats['roulette'])}")

        # Check other core categories
        self.assertGreaterEqual(len(cats["night"]), 100)
        self.assertGreaterEqual(len(cats["maid"]), 100)
        self.assertGreaterEqual(len(cats["schizo"]), 100)
        self.assertGreaterEqual(len(cats["calm"]), 150)
        self.assertGreaterEqual(len(cats["newspaper"]), 100)
        self.assertGreaterEqual(len(cats["digest"]), 100)
        self.assertGreaterEqual(len(cats["summary"]), 100)
        self.assertGreaterEqual(len(cats["stats"]), 100)

    def test_new_thematic_categories_present(self):
        new_themes = ["cyberpunk", "retro", "matrix", "anime", "gothic", "chill", "market", "games", "cards", "duel"]
        for theme in new_themes:
            self.assertIn(theme, CATEGORY_PATTERNS)
            self.assertIn(theme, _CATEGORIZED_BANNERS)
            self.assertGreater(len(_CATEGORIZED_BANNERS[theme]), 0, f"Theme {theme} should have banners")

    def test_get_banner_file_for_all_categories(self):
        for cat in _CATEGORIZED_BANNERS:
            fname, payload = get_banner_file(category=cat)
            self.assertTrue(fname, f"Category {cat} returned empty filename")
            self.assertTrue(payload, f"Category {cat} returned empty payload")
            self.assertTrue((BANNERS_DIR / fname).exists(), f"Banner {fname} does not exist in {BANNERS_DIR}")

    def test_anti_repeat_shuffle_bag(self):
        user_id = 999888
        seen = []
        for _ in range(5):
            fname, _ = get_banner_file(category="shop", user_id=user_id)
            seen.append(fname)
        # Banners returned for same user should avoid immediate duplicate
        self.assertEqual(len(seen), len(set(seen)), "Expected distinct banners across 5 consecutive calls")


if __name__ == "__main__":
    unittest.main()
