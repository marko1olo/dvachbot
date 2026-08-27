# -*- coding: utf-8 -*-
"""Tests for bayan detection, exponential shadowmute, and /wipe auto-shadowmute."""
import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from common.spam_filter import (
    check_bayan, _bayan_tracker, _bayan_mute_count, _bayan_mute_last_ts,
    _content_fingerprint, get_bayan_escalation_level,
    BAYAN_THRESHOLD, BAYAN_BASE_MUTE_SEC, BAYAN_WINDOW_SEC,
    SpamResult, analyze_message_for_spam,
)


def _reset_bayan_state(user_id: int):
    """Reset bayan tracking state for a user."""
    _bayan_tracker[user_id].clear()
    _bayan_mute_count[user_id] = 0
    _bayan_mute_last_ts[user_id] = 0.0


class TestContentFingerprint:
    def test_media_fingerprint(self):
        fp = _content_fingerprint("AgACAgIAAxkBDR6u", "photo")
        assert fp == "media:AgACAgIAAxkBDR6u"

    def test_text_fingerprint_normalized(self):
        fp1 = _content_fingerprint("Hello World", "text")
        fp2 = _content_fingerprint("hello world", "text")
        fp3 = _content_fingerprint("  Hello World  ", "text")
        assert fp1 == fp2 == fp3

    def test_text_too_short_ignored(self):
        fp = _content_fingerprint("hi", "text")
        assert fp == ""

    def test_different_content_different_fp(self):
        fp1 = _content_fingerprint("First message content", "text")
        fp2 = _content_fingerprint("Second completely different text", "text")
        assert fp1 != fp2


class TestBayanDetection:
    def setup_method(self):
        _reset_bayan_state(999)

    def test_no_bayan_under_threshold(self):
        """2 identical posts should NOT trigger bayan."""
        is_bayan, _ = check_bayan(999, "AgACAgIAAxkBDR6u", "photo")
        assert not is_bayan
        is_bayan, _ = check_bayan(999, "AgACAgIAAxkBDR6u", "photo")
        assert not is_bayan

    def test_bayan_at_threshold(self):
        """3 identical posts should trigger bayan."""
        check_bayan(999, "AgACAgIAAxkBDR6u", "photo")
        check_bayan(999, "AgACAgIAAxkBDR6u", "photo")
        is_bayan, mute_sec = check_bayan(999, "AgACAgIAAxkBDR6u", "photo")
        assert is_bayan
        assert mute_sec == BAYAN_BASE_MUTE_SEC  # 1200 seconds = 20 minutes

    def test_bayan_text_duplicates(self):
        """3 identical text messages should trigger bayan."""
        _reset_bayan_state(998)
        check_bayan(998, "Спам текст для проверки бояна", "text")
        check_bayan(998, "Спам текст для проверки бояна", "text")
        is_bayan, mute_sec = check_bayan(998, "спам текст для проверки бояна", "text")  # Case-insensitive
        assert is_bayan
        assert mute_sec == BAYAN_BASE_MUTE_SEC

    def test_different_content_no_bayan(self):
        """3 different posts should NOT trigger bayan."""
        check_bayan(999, "photo_id_1", "photo")
        check_bayan(999, "photo_id_2", "photo")
        is_bayan, _ = check_bayan(999, "photo_id_3", "photo")
        assert not is_bayan

    def test_exponential_escalation(self):
        """Repeated bayan offenses should double the mute duration."""
        # First offense: 20 min
        check_bayan(999, "spam1", "photo")
        check_bayan(999, "spam1", "photo")
        is_bayan, mute1 = check_bayan(999, "spam1", "photo")
        assert is_bayan
        assert mute1 == 1200  # 20 min

        # Second offense: 40 min
        check_bayan(999, "spam2", "photo")
        check_bayan(999, "spam2", "photo")
        is_bayan, mute2 = check_bayan(999, "spam2", "photo")
        assert is_bayan
        assert mute2 == 2400  # 40 min

        # Third offense: 80 min
        check_bayan(999, "spam3", "photo")
        check_bayan(999, "spam3", "photo")
        is_bayan, mute3 = check_bayan(999, "spam3", "photo")
        assert is_bayan
        assert mute3 == 4800  # 80 min

    def test_escalation_cap_at_24h(self):
        """Escalation should cap at 24 hours."""
        _reset_bayan_state(997)
        # Manually set high escalation count
        _bayan_mute_count[997] = 20  # 2^20 * 1200 would be absurdly high
        _bayan_mute_last_ts[997] = time.time()  # Recent, so no reset
        
        check_bayan(997, "spam_cap", "photo")
        check_bayan(997, "spam_cap", "photo")
        is_bayan, mute_sec = check_bayan(997, "spam_cap", "photo")
        assert is_bayan
        assert mute_sec == 86400  # 24 hours cap

    def test_escalation_resets_after_cooldown(self):
        """Escalation counter resets after BAYAN_RESET_SEC of no mutes."""
        # First offense
        check_bayan(999, "spam_reset", "photo")
        check_bayan(999, "spam_reset", "photo")
        is_bayan, mute1 = check_bayan(999, "spam_reset", "photo")
        assert is_bayan
        assert mute1 == 1200

        # Simulate time passing beyond reset window
        _bayan_mute_last_ts[999] = time.time() - 3700  # > 3600 sec reset

        # Next offense should be back to base
        check_bayan(999, "spam_reset2", "photo")
        check_bayan(999, "spam_reset2", "photo")
        is_bayan, mute2 = check_bayan(999, "spam_reset2", "photo")
        assert is_bayan
        assert mute2 == 1200  # Back to base


class TestBayanEscalationLevel:
    def setup_method(self):
        _reset_bayan_state(888)

    def test_initial_level_zero(self):
        assert get_bayan_escalation_level(888) == 0

    def test_level_increments_on_bayan(self):
        check_bayan(888, "same", "photo")
        check_bayan(888, "same", "photo")
        check_bayan(888, "same", "photo")
        assert get_bayan_escalation_level(888) == 1


class TestSpamResultEnum:
    def test_bayan_mute_exists(self):
        assert hasattr(SpamResult, 'BAYAN_MUTE')


@pytest.mark.asyncio
async def test_analyze_message_bayan_integration():
    """Integration test: analyze_message_for_spam returns BAYAN_MUTE for duplicate content."""
    _reset_bayan_state(777)
    
    # Mock is_admin to always return False
    import common.spam_filter as sf
    
    # Send 3 identical photos
    r1, _ = await sf.analyze_message_for_spam(777, 'test_board', 'AgACAgIPhoto123', 'photo', 'photo')
    assert r1 == SpamResult.CLEAN
    
    r2, _ = await sf.analyze_message_for_spam(777, 'test_board', 'AgACAgIPhoto123', 'photo', 'photo')
    assert r2 == SpamResult.CLEAN
    
    r3, level = await sf.analyze_message_for_spam(777, 'test_board', 'AgACAgIPhoto123', 'photo', 'photo')
    assert r3 == SpamResult.BAYAN_MUTE
    assert level == BAYAN_BASE_MUTE_SEC  # 1200


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
