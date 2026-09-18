# -*- coding: utf-8 -*-
"""
tests/test_cyberchad_dynamic_tuning.py — Verification of:
1. Base cooldown reduction to 30.0s.
2. Active user cooldown (>=10 posts or is_verified_b) dropped to 10.0s.
3. Elimination of noisy public TTS voice bombing on rate limit hits.
"""
import time
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import shared_state
from handlers.message_router import (
    trigger_cyberchad_with_rate_limit,
    _CYBERCHAD_USER_LAST_DIRECT,
    _CYBERCHAD_USER_LAST_REJECT,
)

@pytest.fixture(autouse=True)
def clean_chad_state():
    _CYBERCHAD_USER_LAST_DIRECT.clear()
    _CYBERCHAD_USER_LAST_REJECT.clear()
    yield
    _CYBERCHAD_USER_LAST_DIRECT.clear()
    _CYBERCHAD_USER_LAST_REJECT.clear()


@pytest.mark.asyncio
async def test_cyberchad_base_cooldown_30s_and_no_voice_bomb():
    """Verify standard user gets 30s cooldown and NO voice bombing on reject."""
    mock_bot = AsyncMock()
    now = 100000.0

    mock_db = AsyncMock()
    mock_cursor = AsyncMock()
    mock_cursor.fetchone = AsyncMock(return_value=(2, 0))  # 2 posts, not verified -> standard user
    mock_db.execute = AsyncMock(return_value=mock_cursor)

    with patch("handlers.message_router.register_post_and_maybe_trigger_cyberchad_intervention", new_callable=AsyncMock) as mock_intervene, \
         patch("handlers.message_router.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock) as mock_tts, \
         patch("handlers.message_router.process_new_post", new_callable=AsyncMock) as mock_pnp, \
         patch("common.db_pool.get_pool", return_value=mock_db), \
         patch("time.time", return_value=now):

        # First trigger at t=0: Allowed
        res1 = await trigger_cyberchad_with_rate_limit(mock_bot, "b", 123, "киберчед привет", post_num=10)
        assert res1 is True
        assert mock_intervene.call_count == 1
        assert mock_tts.call_count == 0
        assert mock_pnp.call_count == 0

        # Trigger at t=15s: Standard user is on 30s cooldown -> BLOCKED, NO VOICE BOMB!
        with patch("time.time", return_value=now + 15.0):
            res2 = await trigger_cyberchad_with_rate_limit(mock_bot, "b", 123, "киберчед привет 2", post_num=11)
            assert res2 is False
            assert mock_intervene.call_count == 1
            # CRITICAL: Voice bombing must be ELIMINATED
            assert mock_tts.call_count == 0
            assert mock_pnp.call_count == 0

        # Trigger at t=31s: Cooldown passed (>=30s) -> ALLOWED
        with patch("time.time", return_value=now + 31.0):
            res3 = await trigger_cyberchad_with_rate_limit(mock_bot, "b", 123, "киберчед привет 3", post_num=12)
            assert res3 is True
            assert mock_intervene.call_count == 2
            assert mock_tts.call_count == 0
            assert mock_pnp.call_count == 0


@pytest.mark.asyncio
async def test_cyberchad_active_user_cooldown_10s():
    """Verify active user (>=10 posts) gets reduced 10s cooldown."""
    mock_bot = AsyncMock()
    now = 200000.0

    mock_db = AsyncMock()
    mock_cursor = AsyncMock()
    mock_cursor.fetchone = AsyncMock(return_value=(15, 0))  # 15 posts -> active user
    mock_db.execute = AsyncMock(return_value=mock_cursor)

    with patch("handlers.message_router.register_post_and_maybe_trigger_cyberchad_intervention", new_callable=AsyncMock) as mock_intervene, \
         patch("handlers.message_router.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock) as mock_tts, \
         patch("handlers.message_router.process_new_post", new_callable=AsyncMock) as mock_pnp, \
         patch("common.db_pool.get_pool", return_value=mock_db), \
         patch("time.time", return_value=now):

        # First trigger at t=0: Allowed
        res1 = await trigger_cyberchad_with_rate_limit(mock_bot, "b", 456, "киберчед база", post_num=20)
        assert res1 is True
        assert mock_intervene.call_count == 1

        # Trigger at t=5s: Active user cooldown is 10s -> Blocked at 5s, silent
        with patch("time.time", return_value=now + 5.0):
            res2 = await trigger_cyberchad_with_rate_limit(mock_bot, "b", 456, "киберчед быстро", post_num=21)
            assert res2 is False
            assert mock_intervene.call_count == 1
            assert mock_tts.call_count == 0

        # Trigger at t=11s: Active user cooldown passed (>=10s) -> ALLOWED!
        with patch("time.time", return_value=now + 11.0):
            res3 = await trigger_cyberchad_with_rate_limit(mock_bot, "b", 456, "киберчед 10сек прошло", post_num=22)
            assert res3 is True
            assert mock_intervene.call_count == 2
