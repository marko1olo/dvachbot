# -*- coding: utf-8 -*-
"""
tests/test_antispam_and_votemute_repairs.py
===========================================
Verification test suite for AntiSpam, Votemute, and Moderation repairs:
1. Permanent invite/promo/scam filter for posts_count < 50 with URL_WHITELIST strictly preserved.
2. Keysmash detector false positive elimination (posts_count >= 100 exemption, letters 'м', 'у', 'о', '.').
3. Burst flood fair tier_burst without artificial min(tier_burst, 5) clamping.
4. Bayan sticker threshold increased to 5 and base mute reduced to 120s.
5. Votemute quorum reform: MIN_POSTS_REQUIRED_FOR_QUORUM = 5, 7-day window.
6. Victim 1-hour immunity via set_partyvan_victim_immunity(target_id, now + 3600).
7. Disabling votemute banner PM spam broadcast (ENABLE_VOTEMUTE_PM_BROADCAST = False).
8. Elimination of toxic sexual auto-replacements in moderation_config.py.
"""

import time
import re
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import common.spam_filter as sf
import votemute_engine as ve
import moderation_config as mc
from post_helpers import apply_shadow_autoreplace


# =============================================================================
# 1. INVITE & PROMO & SCAM FILTER (common/spam_filter.py)
# =============================================================================

def test_antispam_invite_link_blocked_for_newbies():
    """Users with posts_count < 50 posting Telegram invite links must be blocked."""
    is_spam, reason = sf.check_link_or_ad_spam(
        user_id=101, board_id="b", text="Вступайте в закрытый чат: t.me/+SecretInviteKey123", posts_count=10
    )
    assert is_spam is True
    assert "инвайт" in reason.lower() or "telegram" in reason.lower()


def test_antispam_promo_channel_blocked_for_newbies():
    """Users with posts_count < 50 posting Telegram channel promos must be blocked."""
    is_spam, reason = sf.check_link_or_ad_spam(
        user_id=102, board_id="b", text="Подписывайтесь на t.me/super_crypto_channel", posts_count=20
    )
    assert is_spam is True
    assert "промо" in reason.lower() or "telegram" in reason.lower() or "реклама" in reason.lower()


def test_antispam_ad_scam_keywords_blocked_for_newbies():
    """Users with posts_count < 50 posting casino/scam keywords must be blocked."""
    is_spam, reason = sf.check_link_or_ad_spam(
        user_id=103, board_id="b", text="Лучшие ставки на спорт и 1xbet промокод на депозит!", posts_count=5
    )
    assert is_spam is True
    assert "скам" in reason.lower() or "реклам" in reason.lower()


def test_antispam_whitelisted_urls_allowed_for_newbies():
    """Whitelisted domains (tgchan_archive, tgach.top, 2ch.hk) must NOT be blocked."""
    for wl_url in ["https://t.me/tgchan_archive", "https://tgach.top/b/", "https://2ch.hk/b/"]:
        is_spam, reason = sf.check_link_or_ad_spam(
            user_id=104, board_id="b", text=f"Смотри пост в архиве: {wl_url}", posts_count=5
        )
        assert is_spam is False, f"Whitelisted URL {wl_url} was incorrectly flagged: {reason}"


def test_antispam_trusted_users_exempt_from_invite_promo_filter():
    """Users with posts_count >= 50 are trusted and not blocked by the promo filter."""
    is_spam, reason = sf.check_link_or_ad_spam(
        user_id=105, board_id="b", text="Вот мой канал: t.me/friendly_dev_blog", posts_count=60
    )
    assert is_spam is False


# =============================================================================
# 2. KEYSMASH & REPEATED LETTERS FALSE POSITIVES
# =============================================================================

def test_keysmash_slang_tokens_allowed():
    """Repeated 'м', 'у', 'о', and '.' must be recognized as valid tokens."""
    for token in ["ммм", "мммм", "ммммм", "mmm", "mmmm"]:
        assert sf.is_laughter_or_slang_token(token) is True
        assert sf.is_actual_keysmash_or_gibberish(token) is False

    for token in ["ууу", "уууу", "ууууу", "uuu", "uuuu"]:
        assert sf.is_laughter_or_slang_token(token) is True
        assert sf.is_actual_keysmash_or_gibberish(token) is False

    for token in ["ооо", "оооо", "ооооо", "ooo", "oooo"]:
        assert sf.is_laughter_or_slang_token(token) is True
        assert sf.is_actual_keysmash_or_gibberish(token) is False

    for token in ["....", ".....", "......"]:
        assert sf.is_actual_keysmash_or_gibberish(token) is False


def test_keysmash_veterans_exempt_from_hard_keysmash():
    """Users with posts_count >= 100 must be exempt from keysmash detection."""
    gibberish = "asdfghjklфывапрол"
    # For user with 0 posts, keysmash triggers
    assert sf.is_actual_keysmash_or_gibberish(gibberish, posts_count=0) is True

    # For veteran with >= 100 posts, keysmash returns False
    assert sf.is_actual_keysmash_or_gibberish(gibberish, posts_count=100) is False
    assert sf.is_actual_keysmash_or_gibberish(gibberish, posts_count=250) is False

    # check_short_gibberish_flood returns (False, "", 0) for veterans
    is_flood, _, mute_sec = sf.check_short_gibberish_flood(
        user_id=201, text=gibberish, posts_count=100
    )
    assert is_flood is False
    assert mute_sec == 0


# =============================================================================
# 3. BURST FLOOD FAIR TIER LIMITS (NO min(tier_burst, 5) CLAMP)
# =============================================================================

def test_burst_flood_fair_tier_limit():
    """Burst flood for newbie (burst_limit=8) must allow up to 8 messages without artificial clamp."""
    user_id = 301
    board_id = "b"
    sf._user_request_timestamps[user_id].clear()
    now = time.time()

    # Post 8 messages within 3 seconds for newbie (< 500 posts, tier_burst=8)
    for i in range(8):
        is_flood, reason = sf.check_flood(
            user_id=user_id,
            board_id=board_id,
            now_ts=now + (i * 0.3),
            posts_count=10,
            is_media=False,
            is_reply=False
        )
        assert is_flood is False, f"Message {i+1}/8 was incorrectly flagged as burst flood: {reason}"

    # 9th message exceeds burst_limit=8 and triggers flood
    is_flood, reason = sf.check_flood(
        user_id=user_id,
        board_id=board_id,
        now_ts=now + 2.5,
        posts_count=10,
        is_media=False,
        is_reply=False
    )
    assert is_flood is True
    assert "Burst флуд" in reason


# =============================================================================
# 4. BAYAN / STICKER REPETITION LIMITS
# =============================================================================

def test_bayan_sticker_threshold_and_duration():
    """Stickers have threshold=5 within 180s and base mute=120s."""
    user_id = 401
    sf._bayan_tracker[user_id].clear()
    sf._bayan_mute_count[user_id] = 0
    sf._bayan_mute_last_ts[user_id] = 0.0
    now = time.time()

    sticker_file_id = "CAACAgIAAxkBAAEStickerSample123"

    # Up to 4 identical stickers must NOT trigger mute
    for i in range(4):
        is_bayan, mute_sec = sf.check_bayan(
            user_id=user_id,
            msg_type="sticker",
            file_unique_id=sticker_file_id,
            now_ts=now + (i * 2.0)
        )
        assert is_bayan is False
        assert mute_sec == 0

    # 5th identical sticker triggers bayan with base duration 120s (not 1200s!)
    is_bayan, mute_sec = sf.check_bayan(
        user_id=user_id,
        msg_type="sticker",
        file_unique_id=sticker_file_id,
        now_ts=now + 10.0
    )
    assert is_bayan is True
    assert mute_sec == 120  # Reduced base mute for stickers


# =============================================================================
# 5. VOTEMUTE QUORUM REFORM (MIN_POSTS_REQUIRED_FOR_QUORUM = 5, 7 DAYS)
# =============================================================================

@pytest.mark.asyncio
async def test_votemute_quorum_eligibility_five_posts_required(isolated_test_db):
    """Votemute quorum requires >= 5 posts on the board within 7 days."""
    db = isolated_test_db
    board_id = "b"
    await db.execute("INSERT OR IGNORE INTO Boards (board_id, name) VALUES (?, ?)", (board_id, board_id))

    # User 501 with 4 posts (below quorum of 5)
    user_subquorum = 501
    for i in range(4):
        await db.execute(
            "INSERT INTO Posts (board_id, author_id, content, timestamp, is_shadow) VALUES (?, ?, '{}', ?, 0)",
            (board_id, user_subquorum, time.time() - (i * 3600))
        )
    await db.commit()

    is_eligible, reason = await ve.check_voter_eligibility(user_subquorum, board_id, db=db)
    assert is_eligible is False
    assert reason == ve.QUORUM_ELIGIBILITY_ERROR
    assert "не менее 5 постов" in reason
    assert "7 дней" in reason

    # User 502 with 5 posts (meets quorum)
    user_eligible = 502
    for i in range(5):
        await db.execute(
            "INSERT INTO Posts (board_id, author_id, content, timestamp, is_shadow) VALUES (?, ?, '{}', ?, 0)",
            (board_id, user_eligible, time.time() - (i * 3600))
        )
    await db.commit()

    is_eligible, reason = await ve.check_voter_eligibility(user_eligible, board_id, db=db)
    assert is_eligible is True
    assert reason == ""


# =============================================================================
# 6. VICTIM 1-HOUR IMMUNITY AFTER VOTEMUTE
# =============================================================================

@pytest.mark.asyncio
async def test_votemute_victim_immunity_protection(isolated_test_db):
    """Victim receives 1-hour immunity protecting from repeated votemutes."""
    db = isolated_test_db
    board_id = "b"
    target_id = 601
    post_num = 60001
    now = time.time()

    from shared_state import set_partyvan_victim_immunity, get_partyvan_victim_immunity

    # Set 1-hour victim immunity
    set_partyvan_victim_immunity(target_id, now + 3600)
    assert get_partyvan_victim_immunity(target_id) >= now + 3600

    # Attempting to start or add vote against immune target must be rejected
    with patch("votemute_engine.get_pool", return_value=db):
        ok, msg, votes, executed = await ve.start_or_add_vote(
            board_id=board_id,
            target_id=target_id,
            post_num=post_num,
            voter_id=701,
            check_eligibility=False
        )
    assert ok is False
    assert "иммунитет" in msg.lower()


# =============================================================================
# 7. DISABLE PM BANNER BROADCAST
# =============================================================================

@pytest.mark.asyncio
async def test_votemute_pm_banner_broadcast_disabled(isolated_test_db):
    """ENABLE_VOTEMUTE_PM_BROADCAST must be False to prevent PM spam on every votemute."""
    db = isolated_test_db
    assert ve.ENABLE_VOTEMUTE_PM_BROADCAST is False

    mock_msg = AsyncMock()
    mock_msg.from_user = MagicMock(id=801)
    mock_msg.chat = MagicMock(id=-100123456789)
    mock_msg.text = "/votemute 12345"
    mock_msg.reply_to_message = None
    mock_msg.answer = AsyncMock()
    mock_msg.bot = AsyncMock()

    bcast_mock = AsyncMock()
    with patch("votemute_engine.get_pool", return_value=db), \
         patch("banner_manager.broadcast_banner_to_users", bcast_mock), \
         patch("votemute_engine.check_voter_eligibility", return_value=(True, "")), \
         patch("votemute_engine._resolve_target_from_message", return_value=(12345, 802)), \
         patch("votemute_engine.start_or_add_vote", return_value=(True, "ok", 1, False)):
        await ve.cmd_votemute(mock_msg, board_id="b")

    # Give any spawned background task time to run
    await asyncio.sleep(0.05)

    # broadcast_banner_to_users must NOT be called
    assert bcast_mock.call_count == 0, "broadcast_banner_to_users was unexpectedly called!"


# =============================================================================
# 8. MODERATION CONFIG TOXIC AUTOREPLACE REMOVED
# =============================================================================

def test_moderation_config_toxic_replacements_eliminated():
    """Toxic sexual auto-replacements must be completely disabled and eliminated."""
    # SHADOW_WORDS_REGEX must never match common words like 'кал', 'дерьмо', 'баян'
    for test_word in ["кал", "каловые массы", "дерьмо", "баян", "боян", "kal"]:
        assert mc.SHADOW_WORDS_REGEX.search(test_word) is None

    # SHADOW_REPLACEMENTS must not contain degrading sexual slurs
    forbidden_tokens = ["сперм", "хуесос", "сосать", "минет", "пиздолиз", "шлюх"]
    for phrase in mc.SHADOW_REPLACEMENTS:
        lower_p = phrase.lower()
        for token in forbidden_tokens:
            assert token not in lower_p, f"Found toxic sexual term '{token}' in phrase: '{phrase}'"

    # apply_shadow_autoreplace does not replace words with sexual slurs
    content = {"text": "этот пост полный баян и кал"}
    result = apply_shadow_autoreplace(content)
    assert result["text"] == "этот пост полный баян и кал"  # preserved, not corrupted!
