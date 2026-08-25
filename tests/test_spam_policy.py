# -*- coding: utf-8 -*-
import pytest
from datetime import datetime, timedelta, UTC
from common.spam_filter import (
    SPAM_RULES,
    analyze_message_for_spam,
    SpamResult,
    _spam_violations
)


@pytest.mark.asyncio
async def test_spam_rules_media_and_decay():
    # 1. Media rules present
    assert 'photo' in SPAM_RULES
    assert 'video' in SPAM_RULES
    assert 'media' in SPAM_RULES
    assert SPAM_RULES['video']['max_per_window'] >= 15

    # 2. Decay test
    user_id = 999888777
    board_id = 'test_decay_board'
    _spam_violations[board_id][user_id] = {
        'level': 5,
        'last_reset': datetime.now(UTC) - timedelta(minutes=6)
    }

    res, lvl = await analyze_message_for_spam(user_id, board_id, "hello world test", "text", "text", skip_cross_board=True)
    assert res == SpamResult.CLEAN
    assert _spam_violations[board_id][user_id]['level'] == 0
