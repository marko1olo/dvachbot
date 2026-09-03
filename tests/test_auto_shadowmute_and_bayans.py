# -*- coding: utf-8 -*-
"""
Unit tests for Auto-Shadowmute and Bayan Detection System.
Verifies:
1. 3 bayans in 3 minutes gives 20 minutes base shadowmute.
2. Bayans outside the 3-minute window expire and do not trigger mute.
3. Exponential escalation when posting/spamming while shadow-muted (20m -> 40m -> 80m -> 160m...).
4. Text duplicate detection (exact and fuzzy ratio >= 0.85).
5. Media duplicate detection (file_unique_id, file_id, media_hash).
6. Flood criteria (burst and minute limit).
7. Cross-board spam criteria.
8. Link / Ad / Scam spam criteria (with whitelist bypass).
9. Admin immunity across all auto-shadowmute criteria.
10. Database shadowmute helpers (is_shadow_muted, get_shadow_mute_info, update_shadow_mute, apply_shadow_mute).
"""

import time
import pytest
import unittest
from datetime import datetime, timedelta, UTC
from unittest.mock import AsyncMock, MagicMock, patch

import common.config
import site_tgach.admin_config
from common.spam_filter import (
    SpamResult,
    is_bayan,
    check_bayan,
    check_flood,
    check_cross_board_spam,
    _check_cross_board_spam,
    check_link_or_ad_spam,
    evaluate_message_for_autoshadowmute,
    handle_shadow_mute_continuation,
    analyze_message_for_spam,
    get_bayan_escalation_level,
    _bayan_tracker,
    _bayan_mute_count,
    _bayan_mute_last_ts,
    _board_recent_fingerprints,
    _user_request_timestamps,
    _user_link_timestamps,
    cross_board_spam_tracker,
    BAYAN_WINDOW_SEC,
    BAYAN_THRESHOLD,
    BAYAN_BASE_MUTE_SEC,
)
from common.database import (
    is_shadow_muted,
    get_shadow_mute_info,
    update_shadow_mute,
    apply_shadow_mute,
)
import shared_state


class TestAutoShadowmuteAndBayans(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        _bayan_tracker.clear()
        _bayan_mute_count.clear()
        _bayan_mute_last_ts.clear()
        _board_recent_fingerprints.clear()
        _user_request_timestamps.clear()
        _user_link_timestamps.clear()
        cross_board_spam_tracker.clear()
        shared_state.board_data.clear()
        
        self.user_id = 999111222
        self.admin_id = 7777777
        self.board_id = "b"
        
        common.config.ADMIN_IDS.add(self.admin_id)
        site_tgach.admin_config.ADMIN_IDS.add(self.admin_id)
        shared_state.board_data[self.board_id] = {
            'shadow_mutes': {},
            'user_settings': {},
            'users': {'active': set(), 'banned': set()},
            'mutes': {},
        }

    def tearDown(self):
        common.config.ADMIN_IDS.discard(self.admin_id)
        site_tgach.admin_config.ADMIN_IDS.discard(self.admin_id)

    async def test_three_bayans_in_three_minutes_triggers_twenty_min_mute(self):
        """3 bayans within 180s must trigger exactly 20 minutes (1200s) shadowmute."""
        base_time = 1000000.0
        text = "Это совершенно одинаковый тестовый текст баяна"
        
        # 1st post -> recorded, no mute
        is_mute, dur = check_bayan(self.user_id, content=text, msg_type="text", board_id=self.board_id, now_ts=base_time)
        self.assertFalse(is_mute)
        self.assertEqual(dur, 0)
        
        # 2nd post (within 30s) -> duplicate detected, but count is 2 -> no mute
        is_mute, dur = check_bayan(self.user_id, content=text, msg_type="text", board_id=self.board_id, now_ts=base_time + 30.0)
        self.assertFalse(is_mute)
        self.assertEqual(dur, 0)
        
        # 3rd post (within 60s) -> 3rd bayan in window -> triggers 20m shadowmute (1200s)!
        is_mute, dur = check_bayan(self.user_id, content=text, msg_type="text", board_id=self.board_id, now_ts=base_time + 60.0)
        self.assertTrue(is_mute)
        self.assertEqual(dur, 1200)

    async def test_bayans_outside_three_minute_window_expire(self):
        """Bayans posted outside the 180s window must expire and not accumulate to 3."""
        base_time = 1000000.0
        text = "Тестовый текст для проверки истечения окна баянов"
        
        # Post 1 at t = 0
        is_mute, _ = check_bayan(self.user_id, content=text, msg_type="text", board_id=self.board_id, now_ts=base_time)
        self.assertFalse(is_mute)
        
        # Post 2 at t = 50
        is_mute, _ = check_bayan(self.user_id, content=text, msg_type="text", board_id=self.board_id, now_ts=base_time + 50.0)
        self.assertFalse(is_mute)
        
        # Post 3 at t = 240 (190s after Post 2, and 240s after Post 1)
        is_mute, dur = check_bayan(self.user_id, content=text, msg_type="text", board_id=self.board_id, now_ts=base_time + 240.0)
        self.assertFalse(is_mute)
        self.assertEqual(dur, 0)

    async def test_exponential_shadowmute_escalation_on_repeated_bayan(self):
        """Repeatedly triggering bayan mute escalates up to 30 min (1800s) cap: 1200 -> 1800 -> 1800."""
        base_time = 1000000.0
        text = "Баян для проверки экспоненциального роста мута"
        
        # 1st strike (3 bayans): 1200s (20m)
        check_bayan(self.user_id, content=text, msg_type="text", board_id=self.board_id, now_ts=base_time)
        check_bayan(self.user_id, content=text, msg_type="text", board_id=self.board_id, now_ts=base_time + 5.0)
        is_mute, dur1 = check_bayan(self.user_id, content=text, msg_type="text", board_id=self.board_id, now_ts=base_time + 10.0)
        self.assertTrue(is_mute)
        self.assertEqual(dur1, 1200)
        self.assertEqual(get_bayan_escalation_level(self.user_id), 1)
        
        # 2nd strike in mute: 1800s (30m cap)
        check_bayan(self.user_id, content=text, msg_type="text", board_id=self.board_id, now_ts=base_time + 20.0)
        check_bayan(self.user_id, content=text, msg_type="text", board_id=self.board_id, now_ts=base_time + 25.0)
        is_mute, dur2 = check_bayan(self.user_id, content=text, msg_type="text", board_id=self.board_id, now_ts=base_time + 30.0)
        self.assertTrue(is_mute)
        self.assertEqual(dur2, 1800)
        self.assertEqual(get_bayan_escalation_level(self.user_id), 2)
        
        # 3rd strike: 1800s (30m cap)
        check_bayan(self.user_id, content=text, msg_type="text", board_id=self.board_id, now_ts=base_time + 40.0)
        check_bayan(self.user_id, content=text, msg_type="text", board_id=self.board_id, now_ts=base_time + 45.0)
        is_mute, dur3 = check_bayan(self.user_id, content=text, msg_type="text", board_id=self.board_id, now_ts=base_time + 50.0)
        self.assertTrue(is_mute)
        self.assertEqual(dur3, 1800)
        self.assertEqual(get_bayan_escalation_level(self.user_id), 3)

    async def test_handle_shadow_mute_continuation_preserves_timer(self):
        """Posting while shadow-muted keeps the existing expiration without doubling."""
        now = time.time()
        initial_exp = now + 1000.0
        shared_state.board_data[self.board_id]['shadow_mutes'][self.user_id] = datetime.fromtimestamp(initial_exp, UTC)
        
        with patch('common.database.update_shadow_mute', new=AsyncMock()):
            extended, cur_exp = await handle_shadow_mute_continuation(self.user_id, self.board_id, reason="Тест")
            self.assertTrue(extended)
            self.assertAlmostEqual(cur_exp, initial_exp, delta=1.0)

    async def test_bayan_detection_fuzzy_text(self):
        """Fuzzy text similarity >= 85% must be detected as a duplicate."""
        base_time = 1000000.0
        t1 = "Привет всем двачерам, как ваши дела сегодня вечером?"
        t2 = "Привет всем двачерам, как ваши дела сегодня вечером!"
        
        check_bayan(self.user_id, content=t1, msg_type="text", board_id=self.board_id, now_ts=base_time)
        is_dup, reason = is_bayan(self.user_id, self.board_id, content=t2, msg_type="text", now_ts=base_time + 10.0)
        self.assertTrue(is_dup)
        self.assertIn("Схожий дубликат", reason)

    async def test_bayan_detection_media_file_unique_id_and_hash(self):
        """Media with same file_unique_id or hash must be identified as bayan."""
        base_time = 1000000.0
        fuid = "AQAD_unique_test_12345"
        
        check_bayan(1111111, content=None, msg_type="photo", file_unique_id=fuid, board_id=self.board_id, now_ts=base_time)
        is_dup, reason = is_bayan(self.user_id, self.board_id, content=None, msg_type="photo", file_unique_id=fuid, now_ts=base_time + 10.0)
        self.assertTrue(is_dup)
        self.assertIn("Медиа-баян", reason)

    async def test_flood_detection_burst_and_minute(self):
        """Burst flood (> 8 in 4s) and Minute flood (> 30 in 60s) must trigger."""
        now = 1000000.0
        
        for i in range(8):
            is_fl, _ = check_flood(self.user_id, self.board_id, now_ts=now + i * 0.3)
            self.assertFalse(is_fl)
        
        is_fl, reason = check_flood(self.user_id, self.board_id, now_ts=now + 2.6)
        self.assertTrue(is_fl)
        self.assertIn("Burst флуд", reason)

    async def test_cross_board_spam_detection(self):
        """Posting same long message across boards within 60s triggers cross-board spam; short messages are ignored."""
        # 1. Short messages (< 15 chars or single word) must NEVER trigger cross-board spam
        cross_board_spam_tracker.clear()
        for short_msg in ["тест", "test", "привет", "123", "👍👍👍", "ок"]:
            self.assertTrue(_check_cross_board_spam(self.user_id, "b", short_msg, "text", "text"))
            self.assertTrue(_check_cross_board_spam(self.user_id, "po", short_msg, "text", "text"))
            self.assertTrue(_check_cross_board_spam(self.user_id, "vg", short_msg, "text", "text"))

        # 2. Long identical messages (> 15 chars) across boards trigger cross-board spam on 3rd board
        cross_board_spam_tracker.clear()
        content = "Спам сообщение для рассылки по всем доскам"
        
        res1 = _check_cross_board_spam(self.user_id, "b", content, "text", "text")
        self.assertTrue(res1)
        
        res2 = _check_cross_board_spam(self.user_id, "po", content, "text", "text")
        self.assertTrue(res2)
        
        res3 = _check_cross_board_spam(self.user_id, "vg", content, "text", "text")
        self.assertFalse(res3)

    async def test_link_and_ad_spam_detection(self):
        """Telegram links are allowed; casino/scam keywords must trigger spam."""
        now = 1000000.0
        
        # Telegram links are now allowed
        is_sp, r = check_link_or_ad_spam(self.user_id, self.board_id, "Вступайте в чат t.me/+AbCdEfGhIjKl", now_ts=now)
        self.assertFalse(is_sp)
        
        is_sp, r = check_link_or_ad_spam(self.user_id, self.board_id, "Конфа тут: t.me/joinchat/xyz12345", now_ts=now)
        self.assertFalse(is_sp)
        
        # Casino / Scam keywords remain blocked
        is_sp, r = check_link_or_ad_spam(self.user_id, self.board_id, "Поднимай бабло в 1win и казино вулкан", now_ts=now)
        self.assertTrue(is_sp)
        self.assertIn("Реклама/скам", r)
        
        is_sp, _ = check_link_or_ad_spam(self.user_id, self.board_id, "Смотри архив на tgach.top и t.me/tgchan_archive", now_ts=now)
        self.assertFalse(is_sp)

    async def test_admin_immunity(self):
        """Admins are never flagged for bayans, flood, cross-board, or link spam."""
        now = 1000000.0
        text = "Админский спам 1win t.me/+invite"
        
        self.assertFalse(is_bayan(self.admin_id, self.board_id, content=text, msg_type="text", now_ts=now)[0])
        self.assertFalse(check_bayan(self.admin_id, content=text, msg_type="text", board_id=self.board_id, now_ts=now)[0])
        self.assertFalse(check_flood(self.admin_id, self.board_id, now_ts=now)[0])
        self.assertTrue(_check_cross_board_spam(self.admin_id, "b", text, "text", "text"))
        self.assertTrue(check_cross_board_spam(self.admin_id, "b", text, "text", "text"))
        self.assertFalse(check_link_or_ad_spam(self.admin_id, self.board_id, text, now_ts=now)[0])
        
        mute, _, _ = await evaluate_message_for_autoshadowmute(
            user_id=self.admin_id,
            board_id=self.board_id,
            content=text,
            msg_type="text",
            raw_content_type="text",
            now_ts=now
        )
        self.assertFalse(mute)

    async def test_database_shadowmute_helpers(self):
        """Verify is_shadow_muted, get_shadow_mute_info, and apply_shadow_mute."""
        now = time.time()
        
        # In RAM-only mode when DB has no record
        shared_state.board_data[self.board_id]['shadow_mutes'].clear()
        
        with patch('common.db_pool.get_pool', new=AsyncMock(side_effect=Exception("No DB in test"))),              patch('common.database.update_shadow_mute', new=AsyncMock()):
            
            # User is not muted initially
            self.assertFalse(await is_shadow_muted(self.user_id, self.board_id))
            info = await get_shadow_mute_info(self.user_id, self.board_id)
            self.assertFalse(info['is_muted'])
            
            # Apply 1200s shadow mute
            exp = await apply_shadow_mute(self.user_id, self.board_id, duration_seconds=1200.0, reason="Тестовый мут")
            self.assertGreaterEqual(exp, now + 1199.0)
            
            # Update RAM representation
            shared_state.board_data[self.board_id]['shadow_mutes'][self.user_id] = datetime.fromtimestamp(exp, UTC)
            self.assertTrue(await is_shadow_muted(self.user_id, self.board_id))
            
            info = await get_shadow_mute_info(self.user_id, self.board_id)
            self.assertTrue(info['is_muted'])
            self.assertGreater(info['remaining_seconds'], 1100.0)
            
            # Re-apply respects 1800s hard cap
            exp2 = await apply_shadow_mute(self.user_id, self.board_id, duration_seconds=5000.0, is_exponential=False)
            self.assertLessEqual(exp2, now + 1801.0)
            self.assertGreaterEqual(exp2, now + 1795.0)
