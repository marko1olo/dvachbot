# -*- coding: utf-8 -*-
"""
Unit tests verifying:
'СТИКЕРЫ И ГИФ НЕ БОЛЕЕ 3 ОДИНАКОВЫХ ПОДРЯД'
- Up to 3 identical stickers in a row are allowed.
- 4th identical sticker in a row is blocked as spam.
- Up to 3 identical animations (GIFs) in a row are allowed.
- 4th identical animation in a row is blocked as spam.
- Interrupted sequence (A, A, A, B, A) does not trigger violation.
- Admin bypass.
"""

import time
import pytest
import unittest
from collections import defaultdict, deque

from common.spam_filter import (
    SPAM_RULES,
    _check_repeats,
)
import site_tgach.admin_config


class TestStickerAnimationConsecutiveLimit(unittest.TestCase):
    def setUp(self):
        self.user_id = 12345678
        self.admin_id = 99999999
        site_tgach.admin_config.ADMIN_IDS.add(self.admin_id)
        self.b_data = {
            'last_stickers': defaultdict(lambda: deque(maxlen=20)),
            'last_animations': defaultdict(lambda: deque(maxlen=20)),
            'last_texts': defaultdict(lambda: deque(maxlen=20)),
        }
        self.violations = {'level': 0}

    def tearDown(self):
        site_tgach.admin_config.ADMIN_IDS.discard(self.admin_id)

    def test_spam_rules_max_repeats_is_three_for_stickers_and_animations(self):
        self.assertEqual(SPAM_RULES['sticker']['max_repeats'], 3)
        self.assertEqual(SPAM_RULES['animation']['max_repeats'], 3)

    def test_sticker_up_to_three_allowed_fourth_blocked(self):
        sticker_file_id = "CAACAgIAAxkBAAE123_pepe_sticker_id"
        rules = SPAM_RULES['sticker']

        # 1st sticker: allowed
        res1 = _check_repeats(self.user_id, self.b_data, (sticker_file_id, 'sticker'), rules, self.violations)
        self.assertTrue(res1, "1st sticker must be allowed")
        self.assertEqual(self.violations['level'], 0)

        # 2nd identical sticker in a row: allowed
        res2 = _check_repeats(self.user_id, self.b_data, (sticker_file_id, 'sticker'), rules, self.violations)
        self.assertTrue(res2, "2nd identical sticker in a row must be allowed")
        self.assertEqual(self.violations['level'], 0)

        # 3rd identical sticker in a row: allowed (не более 3 одинаковых подряд!)
        res3 = _check_repeats(self.user_id, self.b_data, (sticker_file_id, 'sticker'), rules, self.violations)
        self.assertTrue(res3, "3rd identical sticker in a row must be allowed")
        self.assertEqual(self.violations['level'], 0)

        # 4th identical sticker in a row: BLOCKED! (более 3 одинаковых подряд)
        res4 = _check_repeats(self.user_id, self.b_data, (sticker_file_id, 'sticker'), rules, self.violations)
        self.assertFalse(res4, "4th identical sticker in a row MUST be blocked!")
        self.assertEqual(self.violations['level'], 1)

    def test_animation_up_to_three_allowed_fourth_blocked(self):
        gif_file_id = "CgACAgIAAxkBAAE456_cat_gif_id"
        rules = SPAM_RULES['animation']

        # 1st GIF: allowed
        self.assertTrue(_check_repeats(self.user_id, self.b_data, (gif_file_id, 'animation'), rules, self.violations))
        # 2nd GIF: allowed
        self.assertTrue(_check_repeats(self.user_id, self.b_data, (gif_file_id, 'animation'), rules, self.violations))
        # 3rd GIF: allowed (не более 3)
        self.assertTrue(_check_repeats(self.user_id, self.b_data, (gif_file_id, 'animation'), rules, self.violations))
        # 4th GIF: BLOCKED!
        self.assertFalse(_check_repeats(self.user_id, self.b_data, (gif_file_id, 'animation'), rules, self.violations))
        self.assertEqual(self.violations['level'], 1)

    def test_interrupted_sticker_sequence_not_blocked(self):
        stk_a = "sticker_A_id"
        stk_b = "sticker_B_id"
        rules = SPAM_RULES['sticker']

        # 3 times A
        self.assertTrue(_check_repeats(self.user_id, self.b_data, (stk_a, 'sticker'), rules, self.violations))
        self.assertTrue(_check_repeats(self.user_id, self.b_data, (stk_a, 'sticker'), rules, self.violations))
        self.assertTrue(_check_repeats(self.user_id, self.b_data, (stk_a, 'sticker'), rules, self.violations))

        # Interrupted by B -> resets consecutive identical sequence!
        self.assertTrue(_check_repeats(self.user_id, self.b_data, (stk_b, 'sticker'), rules, self.violations))

        # Another A -> now only 1 consecutive A, allowed!
        self.assertTrue(_check_repeats(self.user_id, self.b_data, (stk_a, 'sticker'), rules, self.violations))
        self.assertEqual(self.violations['level'], 0)

    def test_admin_bypass_consecutive_repeats(self):
        stk_id = "sticker_admin_id"
        rules = SPAM_RULES['sticker']

        for i in range(10):
            res = _check_repeats(self.admin_id, self.b_data, (stk_id, 'sticker'), rules, self.violations)
            self.assertTrue(res, f"Admin must bypass repeat limits (iteration {i})")
        self.assertEqual(self.violations['level'], 0)
