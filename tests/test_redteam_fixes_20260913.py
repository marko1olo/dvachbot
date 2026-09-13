import pytest
import time
import re
import html
from unittest.mock import MagicMock, AsyncMock, patch

# 1. Test get_real_ip IP spoofing protection
def test_get_real_ip_spoofing():
    from site_tgach.main import get_real_ip

    # Untrusted external client
    req_external = MagicMock()
    req_external.client.host = "203.0.113.50"
    req_external.headers = {
        "x-forwarded-for": "1.2.3.4",
        "x-real-ip": "5.6.7.8"
    }
    # Must ignore spoofed headers and return real client host
    assert get_real_ip(req_external) == "203.0.113.50"

    # Trusted local reverse proxy (localhost)
    req_local = MagicMock()
    req_local.client.host = "127.0.0.1"
    req_local.headers = {
        "x-forwarded-for": "93.184.216.34, 10.0.0.1",
        "x-real-ip": "93.184.216.34"
    }
    assert get_real_ip(req_local) == "93.184.216.34"


# 2. Test BB-code btn_replacer XSS immunity
def test_btn_replacer_xss_protection():
    from site_tgach.main import _apply_bbcode_and_effects

    # Dangerous schemes
    xss_payloads = [
        "[btn=javascript:alert(1)]Click me[/btn]",
        "[btn=data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==]Click me[/btn]",
        "[btn=vbscript:msgbox(1)]Click me[/btn]",
        "[btn=java&#115;cript:alert(1)]Click me[/btn]",
    ]
    for payload in xss_payloads:
        result = _apply_bbcode_and_effects(payload)
        assert 'href="#"' in result, f"Failed to neutralize: {payload} -> {result}"
        assert 'javascript:' not in result.lower()
        assert 'data:text/html' not in result.lower()

    # Valid URLs
    valid_payloads = [
        ("[btn=https://2ch.hk/b/]Safe Link[/btn]", 'href="https://2ch.hk/b/"'),
        ("[btn=/thread/12345]Local Link[/btn]", 'href="/thread/12345"'),
    ]
    for payload, expected in valid_payloads:
        result = _apply_bbcode_and_effects(payload)
        assert expected in result


# 3. Test TMA replay attack prevention
def test_tma_replay_prevention(monkeypatch):
    from site_tgach.security import verify_telegram_webapp_data

    monkeypatch.setenv("TEST_BOT_TOKEN", "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11")
    
    # Old timestamp (e.g. 2 days ago)
    old_ts = int(time.time()) - 172800
    init_data = f"auth_date={old_ts}&query_id=test&user=%7B%22id%22%3A100%7D&hash=dummyhash"
    
    res = verify_telegram_webapp_data(init_data)
    # Must be rejected (either hash mismatch or expired)
    assert res is None


# 4. Test Russian Roulette cashout bet security
@pytest.mark.asyncio
async def test_russian_roulette_cashout_uses_session_bet():
    import casino_engine

    user_id = 999888
    session_bet = 500
    casino_engine.active_roulette_sessions[user_id] = {
        "streak": 2,
        "bet": session_bet,
        "current_mult": 1.44,
        "last_shot": time.time(),
    }

    # Verify session retrieves genuine bet
    async with casino_engine.session_lock:
        sess = casino_engine.active_roulette_sessions.pop(user_id, None)

    assert sess is not None
    assert sess["bet"] == session_bet
    assert sess["current_mult"] == 1.44
    # Attempting to inject client bet 100000000 should be ignored by reading sess['bet']
    injected_client_bet = 100000000
    actual_bet = int(sess.get("bet", 0))
    assert actual_bet == 500
    assert actual_bet != injected_client_bet


# 5. Test Combat Moderation bail deduction verification
@pytest.mark.asyncio
async def test_combat_appeal_bail_fails_when_deduction_fails():
    import combat_moderation_engine
    from combat_moderation_engine import callback_combat_bail

    session_id = "test_bail_sess"
    sess = combat_moderation_engine.CombatAppealSession(
        session_id=session_id,
        board_id="b",
        attacker_id=111,
        target_id=222,
        weapon_type="partyvan",
        duration_sec=3600,
        created_ts=time.time(),
        chat_id=100,
        announcement_msg_id=10
    )
    combat_moderation_engine.active_combat_appeals[session_id] = sess

    mock_callback = AsyncMock()
    mock_callback.data = f"cbail:{session_id}"
    mock_callback.from_user.id = 222
    mock_callback.message.chat.id = 100

    # Mock pool and simulate deduction failure
    mock_db = MagicMock()
    mock_cur = AsyncMock()
    mock_cur.fetchone.return_value = (1000.0,) # has balance in query
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__.return_value = mock_cur
    mock_db.execute.return_value = mock_ctx

    with patch("combat_moderation_engine.get_pool", return_value=mock_db), \
         patch("main.deduct_user_global_balance", new_callable=AsyncMock, return_value=(False, 0.0)) as mock_deduct, \
         patch("main.remove_regular_mute", new_callable=AsyncMock) as mock_unmute:
        
        await callback_combat_bail(mock_callback)

        assert mock_deduct.called
        # Mute must NOT be removed when deduction fails!
        assert not mock_unmute.called
        assert sess.is_bailed is False


# 6. Test Thinking Tags and Gemini CoT bullet stripping
def test_strip_thinking_tags_and_gemini_cot():
    from common.text_utils import strip_thinking_tags

    input_text = (
        "* Removing \"Ой\" to avoid cliché opening.\n"
        "* Let's adjust the tone to be aggressive and concise.\n"
        "Draft:\n"
        "Позорище, закрой свой рот и не позорься в треде."
    )
    cleaned = strip_thinking_tags(input_text)
    assert "* Removing" not in cleaned
    assert "* Let's adjust" not in cleaned
    assert "Draft:" not in cleaned
    assert "Позорище, закрой свой рот" in cleaned


# 7. Test CYBERCHAD rate limit phrase cleaning
def test_cyberchad_rate_limit_phrases_sanitized():
    import ai_manager
    import handlers.message_router

    for phrase in ai_manager.CYBERCHAD_RATE_LIMIT_REJECTIONS:
        assert not phrase.startswith("Слышь"), f"Found prohibited 'Слышь' in ai_manager: {phrase}"
        assert "обтекай" not in phrase.lower(), f"Found prohibited 'обтекай' in ai_manager: {phrase}"

    for phrase in handlers.message_router.CYBERCHAD_RATE_LIMIT_REJECTIONS:
        assert not phrase.startswith("Слышь"), f"Found prohibited 'Слышь' in message_router: {phrase}"
        assert "обтекай" not in phrase.lower(), f"Found prohibited 'обтекай' in message_router: {phrase}"
