# -*- coding: utf-8 -*-
"""
tests/test_adversarial_challenger_hardening.py
=============================================
Comprehensive Adversarial Red Team Test Suite for Challenger Hardening.
Tests hostile attack vectors, exploit payloads, boundary conditions, and race conditions
across all 11 acceptance criteria:

1. Token leak: verify no 307 redirect leaks bot token.
2. Russian roulette shekel dup: verify forged callback cas:rr:cashout:999999999 cannot inflate payout.
3. BB-code XSS: verify [btn=data:text/html,...] and [btn=java&#115;cript:...] are neutralized.
4. IP spoofing: verify spoofed X-Forwarded-For from external host is ignored.
5. TMA auth replay: verify initData with stale auth_date is rejected.
6. Post mapping memory bound: verify message_to_post bounded at 20,000 entries.
7. Message chunking: verify messages >4096 chars are chunked with balanced HTML tags.
8. Cyberchad CoT stripping: verify Removing "...", * Let's ..., New draft: are stripped.
9. Rate-limit insults: verify no 'обтекай' or 'слышь' in active pool.
10. Duel escrow: verify participants cannot freeroll or zero balance.
11. Combat moderation bail: verify zero balance user cannot exit mute.
"""

import asyncio
import hashlib
import hmac
import html
import io
import json
import os
import time
from html.parser import HTMLParser
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import quote

import pytest
from fastapi import HTTPException
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from starlette.requests import Request
from starlette.responses import Response

# Initialize in-memory cache backend for test isolation if needed
try:
    FastAPICache.get_backend()
except Exception:
    FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache")

import shared_state
from shared_state import BoundedDict
import main
import casino_engine
from site_tgach.main import (
    app,
    get_real_ip,
    get_telegram_file,
    format_post_text,
    sanitize_header_filename,
)
from site_tgach.security import verify_telegram_webapp_data
from common.text_chunker import (
    count_tg_utf16_units,
    chunk_html_message,
    safe_html_truncate,
)
from common.text_utils import strip_cot_and_drafts, clean_ai_thinking, strip_thinking_tags
import ai_manager
import handlers.message_router as mr
from common.bot_helpers import accept_duel_logic, decline_duel_logic
from common.database import (
    get_user_global_balance,
    add_user_global_balance,
    deduct_user_global_balance,
    get_abu_fund_total,
)
import combat_moderation_engine as cme
from combat_moderation_engine import (
    create_combat_appeal_session,
    callback_combat_bail,
    reset_combat_moderation_state,
)


# =============================================================================
# HTML Tag Validator Helper
# =============================================================================

class StrictHTMLValidator(HTMLParser):
    """Strictly validates that all opened HTML tags are closed in reverse order."""
    def __init__(self):
        super().__init__()
        self.stack = []
        self.errors = []

    def handle_starttag(self, tag, attrs):
        if tag not in ("br", "hr", "img"):
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack:
            self.errors.append(f"Unexpected closing tag </{tag}>")
        elif self.stack[-1] == tag:
            self.stack.pop()
        else:
            self.errors.append(f"Mismatched closing tag </{tag}>, expected </{self.stack[-1]}>")

    def validate(self, text: str) -> tuple[bool, list[str]]:
        self.reset()
        self.stack.clear()
        self.errors.clear()
        self.feed(text)
        if self.stack:
            self.errors.append(f"Unclosed tags at end: {self.stack}")
        return len(self.errors) == 0, self.errors


@pytest.fixture(autouse=True)
def cleanup_adversarial_states():
    shared_state._active_duels.clear()
    main._duel_cooldowns.clear()
    casino_engine.active_roulette_sessions.clear()
    reset_combat_moderation_state()
    yield
    shared_state._active_duels.clear()
    main._duel_cooldowns.clear()
    casino_engine.active_roulette_sessions.clear()
    reset_combat_moderation_state()


# =============================================================================
# 1. TOKEN LEAK ADVERSARIAL TESTS
# =============================================================================

class TestAdversarialTokenLeak:
    """Adversarial validation that bot tokens are never leaked via 307 redirects or headers."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("client_ip,country", [
        ("198.51.100.22", "US"),
        ("194.67.210.5", "DE"),
        ("133.242.1.1", "JP"),
        ("77.88.55.66", "RU"),
    ])
    async def test_no_307_redirect_leaks_token_across_geographies(self, client_ip, country):
        """Verifies that requests from any country stream media server-side without 307 redirects."""
        dummy_token = "1234567890:AAFl4wM9FakeSecretTokenForTesting"
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/file/AgAC_test_file_adversarial",
            "query_string": b"skip=r2,catbox,0x0,freeimage,imgbb,pixhost",
            "headers": [(b"host", b"tgach.test"), (b"accept-language", b"en-US,en;q=0.9")],
            "client": (client_ip, 49152),
            "app": app,
        }
        req = Request(scope)
        req.state.lang = "en"
        req.state.t = lambda k, **kw: k

        with patch("site_tgach.main.get_country_by_ip", new_callable=AsyncMock) as mock_geo, \
             patch("site_tgach.main.get_file_mirrors", new_callable=AsyncMock) as mock_mirrors, \
             patch("site_tgach.main.get_cached_file_path", new_callable=AsyncMock) as mock_tg, \
             patch("site_tgach.main._proxy_protected_telegram_file", new_callable=AsyncMock) as mock_proxy:
            mock_geo.return_value = country
            mock_mirrors.return_value = {}
            mock_tg.return_value = ("documents/secret_doc.pdf", dummy_token)
            mock_proxy.return_value = Response(content=b"safe_bytes", media_type="application/pdf", status_code=200)

            resp = await get_telegram_file(file_id="AgAC_test_file_adversarial", skip="r2,catbox,0x0,freeimage,imgbb,pixhost", request=req)

            # Assert status is 200 (server-side stream), NOT 307
            assert resp.status_code == 200
            # Assert Location header does not exist or does not contain bot token
            loc = resp.headers.get("location", "")
            assert "api.telegram.org" not in loc
            assert dummy_token not in loc
            # Assert headers do not expose bot token
            for header_k, header_v in resp.headers.items():
                assert dummy_token not in header_v

    @pytest.mark.asyncio
    async def test_upstream_error_does_not_leak_bot_token_in_detail(self, isolated_test_db):
        """If upstream telegram proxy raises an exception, the bot token must never appear in response/logs."""
        dummy_token = "9988776655:SECRET_TOKEN_DO_NOT_LEAK"
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/file/AgAC_fail",
            "query_string": b"skip=r2,catbox,0x0,freeimage,imgbb,pixhost",
            "headers": [],
            "client": ("198.51.100.77", 49152),
            "app": app,
        }
        req = Request(scope)
        req.state.lang = "en"
        req.state.t = lambda k, **kw: k

        with patch("site_tgach.main.get_country_by_ip", new_callable=AsyncMock) as mock_geo, \
             patch("site_tgach.main.get_file_mirrors", new_callable=AsyncMock) as mock_mirrors, \
             patch("site_tgach.main.get_cached_file_path", new_callable=AsyncMock) as mock_tg, \
             patch("site_tgach.main.get_pool", AsyncMock(return_value=isolated_test_db)), \
             patch("site_tgach.main._proxy_protected_telegram_file", new_callable=AsyncMock) as mock_proxy:
            mock_geo.return_value = "US"
            mock_mirrors.return_value = {}
            mock_tg.return_value = ("photos/file.jpg", dummy_token)
            mock_proxy.side_effect = HTTPException(status_code=404, detail="File unavailable.")

            with pytest.raises(HTTPException) as excinfo:
                await get_telegram_file(file_id="AgAC_fail", skip="r2,catbox,0x0,freeimage,imgbb,pixhost", request=req)
            assert dummy_token not in str(excinfo.value.detail)


# =============================================================================
# 2. RUSSIAN ROULETTE SHEKEL DUP ADVERSARIAL TESTS
# =============================================================================

class TestAdversarialRussianRouletteDup:
    """Adversarial red team verification against shekel duplication and callback tampering."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("forged_param", [
        "999999999",
        "-50000",
        "0",
        "NaN",
        "1e9",
        "99999999999999999999999999",
    ])
    async def test_forged_callback_bet_cannot_inflate_payout(self, isolated_test_db, forged_param):
        """Attacker sends cas:rr:cashout:<forged_param>, but payout MUST only be calculated from session bet (100)."""
        db = isolated_test_db
        user_id = 777001
        await add_user_global_balance(db, user_id, "b", 500.0)

        # Seed valid active roulette session with bet = 100 and current_mult = 1.37
        casino_engine.active_roulette_sessions[user_id] = {
            "streak": 2,
            "bet": 100,
            "current_mult": 1.37,
            "last_shot": time.time(),
        }

        cb = AsyncMock()
        cb.from_user.id = user_id
        cb.message.chat.id = 12345
        cb.data = f"cas:rr:cashout:{forged_param}"
        cb.answer = AsyncMock()

        with patch("main.get_pool", AsyncMock(return_value=db)):
            await main.cb_casino_handler(cb, "b")

        # Expected payout: 100 * 1.37 = 137. User initial balance was 500.0.
        # Payout added to balance: 500.0 + 137.0 = 637.0.
        # If forged_param had been used, payout would have been millions.
        new_bal = await get_user_global_balance(db, user_id)
        assert new_bal == 637.0  # Exactly 500.0 + 137.0
        assert user_id not in casino_engine.active_roulette_sessions

    @pytest.mark.asyncio
    async def test_cashout_without_active_session_fails(self, isolated_test_db):
        """Replay attack: cashing out twice or without active session is rejected."""
        db = isolated_test_db
        user_id = 777002
        await add_user_global_balance(db, user_id, "b", 500.0)

        cb = AsyncMock()
        cb.from_user.id = user_id
        cb.message.chat.id = 12345
        cb.data = "cas:rr:cashout:100"
        cb.answer = AsyncMock()

        with patch("main.get_pool", AsyncMock(return_value=db)):
            await main.cb_casino_handler(cb, "b")

        # Balance remains unchanged
        assert await get_user_global_balance(db, user_id) == 500.0
        cb.answer.assert_called_once()
        assert "Сессия не найдена" in cb.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_concurrent_double_cashout_race(self, isolated_test_db):
        """Concurrent cashout requests for the same session: only ONE must succeed."""
        db = isolated_test_db
        user_id = 777003
        await add_user_global_balance(db, user_id, "b", 1000.0)

        casino_engine.active_roulette_sessions[user_id] = {
            "streak": 3,
            "bet": 200,
            "current_mult": 1.63,
            "last_shot": time.time(),
        }

        cb1 = AsyncMock()
        cb1.from_user.id = user_id
        cb1.message.chat.id = 12345
        cb1.data = "cas:rr:cashout:200"
        cb1.answer = AsyncMock()

        cb2 = AsyncMock()
        cb2.from_user.id = user_id
        cb2.message.chat.id = 12345
        cb2.data = "cas:rr:cashout:200"
        cb2.answer = AsyncMock()

        with patch("main.get_pool", AsyncMock(return_value=db)):
            await asyncio.gather(
                main.cb_casino_handler(cb1, "b"),
                main.cb_casino_handler(cb2, "b"),
            )

        # Payout should only happen once: 200 * 1.63 = 326.
        # User initial: 1000. Final: 1000 + 326 = 1326.
        final_bal = await get_user_global_balance(db, user_id)
        assert final_bal == 1326.0

        # One call answered "Сессия не найдена", the other succeeded
        answers = [cb1.answer.call_args[0][0] if cb1.answer.call_args and cb1.answer.call_args[0] else "",
                   cb2.answer.call_args[0][0] if cb2.answer.call_args and cb2.answer.call_args[0] else ""]
        assert any("Сессия не найдена" in a for a in answers)


# =============================================================================
# 3. BB-CODE XSS ADVERSARIAL TESTS
# =============================================================================

class TestAdversarialBBCodeXSS:
    """Adversarial stress-testing of BB-code [btn=...] parser with aggressive XSS vectors."""

    @pytest.mark.parametrize("payload", [
        "[btn=data:text/html,<script>alert(1)</script>]Click[/btn]",
        "[btn=data:image/svg+xml;base64,PHN2ZyBvbmxvYWQ9YWxlcnQoMSk+]SVG[/btn]",
        "[btn=data:text/javascript,alert(1)]JS[/btn]",
        "[btn=java&#115;cript:alert(1)]Click[/btn]",
        "[btn=java&#x73;cript:alert(1)]Click[/btn]",
        "[btn=java&amp;#115;cript:alert(1)]Nested[/btn]",
        "[btn=j&#x0041;v&#x0061;script:alert(1)]Zeros[/btn]",
        "[btn=javascript\x00:alert(1)]NullByte[/btn]",
        "[btn=\t\r\njavascript:alert(1)]Controls[/btn]",
        "[btn=JaVaScRiPt:alert(1)]Case[/btn]",
        "[btn=vbscript:msgbox(1)]VBS[/btn]",
        "[btn=blob:https://evil.com/123]Blob[/btn]",
        "[btn=file:///etc/passwd]File[/btn]",
        "[btn=about:blank]About[/btn]",
        "[btn=//evil.com]ProtoRelative[/btn]",
        "[btn=/\\evil.com]BackslashProto[/btn]",
        r"[btn=/\/evil.com]SlashBackslash[/btn]",
        "[btn=\" onclick=\"alert(1)]AttrInject1[/btn]",
        "[btn=' onmouseover='alert(1)]AttrInject2[/btn]",
    ])
    def test_xss_vectors_neutralized_to_safe_hash(self, payload):
        """All dangerous pseudo-schemes and entity obfuscations must be neutralized to href='#'."""
        result = format_post_text(payload)
        assert 'href="#"' in result, f"Payload {payload} was not neutralized to safe '#': {result}"
        assert "javascript:" not in result.lower()
        assert "data:" not in result.lower()
        assert "vbscript:" not in result.lower()
        assert "blob:" not in result.lower()
        assert "file:" not in result.lower()
        assert "onclick" not in result.lower()
        assert "onmouseover" not in result.lower()
        assert "onfocus" not in result.lower()

    def test_attribute_injection_with_http_is_escaped_safely(self):
        """Even if an attacker attempts URL attribute injection, double quotes are escaped and cannot break out."""
        payload = '[btn=https://google.com" onfocus="alert(1)]AttrInject3[/btn]'
        result = format_post_text(payload)
        # Verify no unescaped attribute injection into <a>
        assert 'onfocus=' not in result
        assert '&quot;' in result
        assert 'class="btn btn-primary btn-small post-btn"' in result

    @pytest.mark.parametrize("safe_bbcode,expected_href", [
        ("[btn=https://2ch.hk]Двач[/btn]", 'href="https://2ch.hk"'),
        ("[btn=http://example.com/page?id=1&ref=tg]Link[/btn]", 'href="http://example.com/page?id=1&amp;ref=tg"'),
        ("[btn=/b/res/12345.html]Тред[/btn]", 'href="/b/res/12345.html"'),
        ("[btn=/tv/random]ТВ[/btn]", 'href="/tv/random"'),
    ])
    def test_safe_urls_correctly_rendered(self, safe_bbcode, expected_href):
        """Legitimate safe URLs (http, https, root-relative) must render properly."""
        result = format_post_text(safe_bbcode)
        assert expected_href in result


# =============================================================================
# 4. IP SPOOFING ADVERSARIAL TESTS
# =============================================================================

class TestAdversarialIPSpoofing:
    """Adversarial testing of client IP extraction against spoofed proxy headers."""

    def _make_req(self, client_host: str, headers: list[tuple[bytes, bytes]]) -> Request:
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": headers,
            "client": (client_host, 12345),
            "app": app,
        }
        return Request(scope)

    @pytest.mark.parametrize("untrusted_ip", [
        "198.51.100.1",
        "203.0.113.5",
        "192.168.1.100",  # LAN host is not local proxy
        "10.0.0.1",
        "172.16.0.5",
        "2001:db8::cafe",
    ])
    def test_untrusted_client_cannot_spoof_ip(self, untrusted_ip):
        """An external or non-localhost client MUST NOT have its headers trusted."""
        req = self._make_req(
            client_host=untrusted_ip,
            headers=[
                (b"x-forwarded-for", b"127.0.0.1, 1.1.1.1"),
                (b"x-real-ip", b"127.0.0.1"),
            ]
        )
        real_ip = get_real_ip(req)
        assert real_ip == untrusted_ip, f"Untrusted client {untrusted_ip} successfully spoofed to {real_ip}"

    @pytest.mark.parametrize("proxy_host", ["127.0.0.1", "::1", "localhost"])
    def test_trusted_localhost_proxy_headers_honored(self, proxy_host):
        """Only localhost reverse proxy headers are honored."""
        req = self._make_req(
            client_host=proxy_host,
            headers=[
                (b"x-real-ip", b"203.0.113.195"),
                (b"x-forwarded-for", b"203.0.113.195, 127.0.0.1"),
            ]
        )
        real_ip = get_real_ip(req)
        assert real_ip == "203.0.113.195"


# =============================================================================
# 5. TMA AUTH REPLAY ADVERSARIAL TESTS
# =============================================================================

class TestAdversarialTMAReplay:
    """Adversarial testing of Telegram Mini App initData authentication against replay attacks."""

    def _generate_init_data(self, bot_token: str, auth_date: int | str | None, custom_fields: dict | None = None) -> str:
        data = {
            "user": '{"id":123456,"first_name":"Anon"}',
            "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        }
        if custom_fields:
            data.update(custom_fields)
        if auth_date is not None:
            data["auth_date"] = str(auth_date)

        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
        secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
        calc_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

        encoded_parts = [f"{k}={quote(str(v))}" for k, v in data.items()]
        encoded_parts.append(f"hash={calc_hash}")
        return "&".join(encoded_parts)

    def test_stale_auth_date_strictly_rejected(self):
        """Tokens older than 86,400s (24h) MUST return None."""
        bot_token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
        now = int(time.time())

        # Exactly 86,401s old (24h + 1s)
        stale_init_data = self._generate_init_data(bot_token, auth_date=now - 86401)
        with patch.dict(os.environ, {"MAIN_BOT_TOKEN": bot_token}):
            res = verify_telegram_webapp_data(stale_init_data)
            assert res is None, "Stale initData (86401s old) was unexpectedly accepted!"

        # 7 days old
        very_stale = self._generate_init_data(bot_token, auth_date=now - 604800)
        with patch.dict(os.environ, {"MAIN_BOT_TOKEN": bot_token}):
            res2 = verify_telegram_webapp_data(very_stale)
            assert res2 is None, "Very old initData (7 days old) was unexpectedly accepted!"

    def test_future_drift_auth_date_rejected(self):
        """Tokens drifting >60s into the future MUST return None."""
        bot_token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
        now = int(time.time())

        # +65s in the future
        future_data = self._generate_init_data(bot_token, auth_date=now + 65)
        with patch.dict(os.environ, {"MAIN_BOT_TOKEN": bot_token}):
            res = verify_telegram_webapp_data(future_data)
            assert res is None, "Future initData (+65s drift) was unexpectedly accepted!"

    def test_missing_or_malformed_auth_date_rejected(self):
        bot_token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"

        # Missing auth_date
        no_date = self._generate_init_data(bot_token, auth_date=None)
        with patch.dict(os.environ, {"MAIN_BOT_TOKEN": bot_token}):
            assert verify_telegram_webapp_data(no_date) is None

        # String auth_date
        bad_date = self._generate_init_data(bot_token, auth_date="twenty_four_hours_ago")
        with patch.dict(os.environ, {"MAIN_BOT_TOKEN": bot_token}):
            assert verify_telegram_webapp_data(bad_date) is None

    def test_fresh_valid_auth_date_accepted(self):
        bot_token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
        now = int(time.time())
        fresh = self._generate_init_data(bot_token, auth_date=now - 30)
        with patch.dict(os.environ, {"MAIN_BOT_TOKEN": bot_token}):
            res = verify_telegram_webapp_data(fresh)
            assert res is not None
            assert int(res["auth_date"]) == now - 30


# =============================================================================
# 6. POST MAPPING MEMORY BOUND ADVERSARIAL TESTS
# =============================================================================

class TestAdversarialPostMappingMemoryBound:
    """Stress testing BoundedDict memory limits under heavy simulated bot traffic."""

    def test_message_to_post_strict_capacity_under_massive_load(self):
        """Pushing 50,000 mappings into message_to_post must keep len strictly <= 20,000."""
        limit = 20000
        bd = BoundedDict(max_size=limit)

        for i in range(50000):
            bd[(12345, i)] = i % 1000

        assert len(bd) == limit
        # Oldest 30,000 keys must be evicted
        assert (12345, 0) not in bd
        assert (12345, 29999) not in bd
        # Latest 20,000 keys must be retained
        assert (12345, 30000) in bd
        assert (12345, 49999) in bd

    def test_bulk_update_and_setdefault_under_pressure(self):
        bd = BoundedDict(max_size=100)
        bulk_data = {f"bulk_{i}": i for i in range(500)}
        bd.update(bulk_data)
        assert len(bd) == 100
        assert "bulk_0" not in bd
        assert "bulk_499" in bd

        # setdefault on existing key should not grow dict
        bd.setdefault("bulk_499", 9999)
        assert len(bd) == 100

        # setdefault on new key evicts oldest
        bd.setdefault("brand_new_key", 1)
        assert len(bd) == 100
        assert "bulk_400" not in bd
        assert "brand_new_key" in bd


# =============================================================================
# 7. MESSAGE CHUNKING & BALANCED HTML TAGS ADVERSARIAL TESTS
# =============================================================================

class TestAdversarialMessageChunking:
    """Adversarial stress-testing of chunk_html_message with nested tags, long lines, and entities."""

    def test_chunk_deeply_nested_tags_remains_balanced(self):
        """Deeply nested tags across 10,000 characters must remain 100% valid HTML in every chunk."""
        para = "Длинный абзац двачерского текста с цитатами, рассуждениями и пастами. " * 30
        nested_block = f"<blockquote><b><i><u>{para}</u></i></b></blockquote>\n\n"
        full_text = nested_block * 5  # ~10,740 characters
        assert len(full_text) > 8000

        chunks = chunk_html_message(full_text, max_chars=3500)
        assert len(chunks) >= 3

        validator = StrictHTMLValidator()
        for idx, chunk in enumerate(chunks):
            # 1. Telegram UTF-16 code units strictly under limit
            units = count_tg_utf16_units(chunk)
            assert units <= 3500, f"Chunk {idx} exceeded max_chars: {units} > 3500"

            # 2. Strict HTML balance (all opened tags closed properly)
            is_valid, errors = validator.validate(chunk)
            assert is_valid, f"Chunk {idx} has invalid HTML tags: {errors}\nChunk content:\n{chunk[:200]}...{chunk[-200:]}"

    def test_chunk_with_astral_emojis_at_boundary(self):
        """Astral plane emojis (2 UTF-16 units) near split boundary must never be sliced."""
        base_text = "А" * 3990 + "🔥💀🎉🚀" + "Б" * 1000
        chunks = chunk_html_message(base_text, max_chars=4000)
        for idx, chunk in enumerate(chunks):
            assert count_tg_utf16_units(chunk) <= 4000
            # Chunk must be valid UTF-8 and UTF-16 without surrogate decode error
            encoded = chunk.encode("utf-16-le")
            decoded = encoded.decode("utf-16-le")
            assert decoded == chunk

    def test_chunk_with_long_a_href_reopened_correctly(self):
        """A link with long URL must be closed and reopened across chunks without corruption."""
        url = "https://example.com/very/long/url/with/lots/of/parameters?q=dvach&token=secret"
        content = f'<a href="{url}">' + ("Длинный текст ссылки " * 100) + '</a>'
        chunks = chunk_html_message(content, max_chars=1000)
        assert len(chunks) > 1

        validator = StrictHTMLValidator()
        for idx, chunk in enumerate(chunks):
            is_valid, errors = validator.validate(chunk)
            assert is_valid, f"Chunk {idx} invalid: {errors}"
            assert chunk.startswith('<a href="') or chunk.endswith('</a>')


# =============================================================================
# 8. CYBERCHAD COT STRIPPING ADVERSARIAL TESTS
# =============================================================================

class TestAdversarialCyberchadCoTStripping:
    """Stress testing LLM CoT stripping against sneaky thinking artifacts and draft revisions."""

    @pytest.mark.parametrize("cot_payload,expected_clean", [
        (
            'Removing "Ой" to avoid sounding weak.\n'
            '* Let\'s make it rough.\n'
            '* *New draft:*\n'
            'Ты жалкое ничтожество.',
            'Ты жалкое ничтожество.'
        ),
        (
            '* Let\'s evaluate the user statement.\n'
            '* Removing polite phrasing.\n'
            'New draft:\n'
            'Хватит ныть, омежка.',
            'Хватит ныть, омежка.'
        ),
        (
            'Draft 1:\n'
            'Let\'s reconsider.\n'
            'Thought: User needs hard reality check.\n'
            'Final draft:\n'
            'Иди проспись, чучело.',
            'Иди проспись, чучело.'
        ),
        (
            '<think>\nInternal reasoning\n</think>\n'
            'Базированный двачерский ответ.',
            'Базированный двачерский ответ.'
        ),
        (
            '&lt;think&gt;\nEscaped reasoning\n&lt;/think&gt;\n'
            'Четкий ответ Киберчеда.',
            'Четкий ответ Киберчеда.'
        ),
        (
            '* Tone: hostile and dismissive\n'
            '* Target: anonymous user\n'
            '* Roast text:\n'
            'Свали с борды нахуй.',
            'Свали с борды нахуй.'
        ),
    ])
    def test_adversarial_cot_stripping(self, cot_payload, expected_clean):
        cleaned = strip_cot_and_drafts(cot_payload)
        assert 'Removing' not in cleaned
        assert "Let's" not in cleaned
        assert 'draft' not in cleaned.lower()
        assert 'think' not in cleaned.lower()
        assert cleaned == expected_clean

    def test_parse_cyberchad_response_with_adversarial_json(self):
        payload = json.dumps({
            "reply": True,
            "text": 'Removing "мягкость".\n* Let\'s punch harder.\nNew draft:\nТы позорище всей семьи.',
            "thought": "Internal LLM thought",
        })
        res = ai_manager.parse_cyberchad_response(payload)
        assert res["reply"] is True
        assert res["text"] == "Ты позорище всей семьи."
        assert "Removing" not in res["text"]


# =============================================================================
# 9. RATE-LIMIT INSULTS ADVERSARIAL TESTS
# =============================================================================

class TestAdversarialRateLimitInsults:
    """Verifies that forbidden toxic words ('обтекай', 'слышь') are 100% eradicated from active pools."""

    FORBIDDEN_WORDS = {"обтекай", "слышь"}

    def test_active_pools_completely_free_of_forbidden_words(self):
        active_lists = [
            ("ai_manager.CYBERCHAD_RATE_LIMIT_REJECTIONS", ai_manager.CYBERCHAD_RATE_LIMIT_REJECTIONS),
            ("mr.CYBERCHAD_RATE_LIMIT_REJECTIONS", mr.CYBERCHAD_RATE_LIMIT_REJECTIONS),
            ("mr._EXTRA_RATE_LIMIT_REJECTIONS", mr._EXTRA_RATE_LIMIT_REJECTIONS),
        ]

        for list_name, phrases in active_lists:
            for idx, phrase in enumerate(phrases):
                phrase_lower = phrase.lower()
                for bad_word in self.FORBIDDEN_WORDS:
                    assert bad_word not in phrase_lower, (
                        f"Forbidden word '{bad_word}' found in {list_name}[{idx}]: '{phrase}'"
                    )

    def test_exact_length_twenty_preserved(self):
        assert len(ai_manager.CYBERCHAD_RATE_LIMIT_REJECTIONS) == 20
        assert len(mr.CYBERCHAD_RATE_LIMIT_REJECTIONS) == 20


# =============================================================================
# 10. DUEL ESCROW ADVERSARIAL TESTS
# =============================================================================

class TestAdversarialDuelEscrow:
    """Adversarial testing of classic duel escrow: preventing freerolls, zero-balance exploits, and money leaks."""

    @pytest.mark.asyncio
    async def test_challenger_cannot_freeroll_with_zero_balance(self, isolated_test_db):
        """Challenger with 0 balance attempting /duel 500 must be rejected."""
        db = isolated_test_db
        user_id = 90001
        # Balance = 0

        msg = AsyncMock()
        msg.from_user.id = user_id
        msg.chat.id = 111
        msg.reply_to_message = None
        msg.answer = AsyncMock()

        await main._handle_duel_create(msg, "b", ["500"])

        # Must not create active duel
        assert user_id not in shared_state._active_duels
        # Must not deduct below zero
        assert await get_user_global_balance(db, user_id) == 0.0
        msg.answer.assert_called_once()
        assert "Не хватает шекелей" in msg.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_acceptor_cannot_freeroll_with_zero_balance(self, isolated_test_db):
        """Acceptor with 0 balance attempting /duel accept must be rejected."""
        db = isolated_test_db
        challenger_id = 90002
        acceptor_id = 90003

        # Challenger has 1000
        await add_user_global_balance(db, challenger_id, "b", 1000.0)
        # Create duel
        shared_state._active_duels[challenger_id] = {
            "amount": 500,
            "target_id": None,
            "ts": time.time(),
            "board_id": "b",
            "msg_id": 1,
            "chat_id": 111,
            "broadcast_msgs": [],
            "escrowed": True,
        }

        # Acceptor balance = 0
        msg = AsyncMock()
        msg.from_user.id = acceptor_id
        msg.chat.id = 111
        msg.answer = AsyncMock()

        with patch("common.bot_helpers.get_pool", AsyncMock(return_value=db)):
            await accept_duel_logic(msg, challenger_id, "b", acceptor_id)

        # Acceptor rejected
        assert await get_user_global_balance(db, acceptor_id) == 0.0
        # Duel remains open for legitimate opponents
        assert challenger_id in shared_state._active_duels
        msg.answer.assert_called_once()
        assert "недостаточно шекелей" in msg.answer.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_duel_escrow_exact_mathematical_conservation(self, isolated_test_db):
        """Sum of Challenger balance + Acceptor balance + Abu Fund before and after must be identical."""
        db = isolated_test_db
        p1 = 90004
        p2 = 90005
        await add_user_global_balance(db, p1, "b", 2000.0)
        await add_user_global_balance(db, p2, "b", 2000.0)

        # Pre-seed achievements to prevent extra cash injections
        for uid in [p1, p2]:
            items = json.dumps({"unlocked_achievements": ["ach_duel_win"], "achievements": ["ach_duel_win"]})
            await db.execute("INSERT OR REPLACE INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 2000.0, ?)", (uid, items))
        await db.commit()

        initial_total = (
            await get_user_global_balance(db, p1) +
            await get_user_global_balance(db, p2) +
            await get_abu_fund_total(db)
        )

        # Step 1: P1 creates duel 600
        msg1 = AsyncMock()
        msg1.from_user.id = p1
        msg1.chat.id = 111
        msg1.reply_to_message = None
        msg1.answer = AsyncMock(return_value=MagicMock(message_id=10, chat=MagicMock(id=111)))

        await main._handle_duel_create(msg1, "b", ["600"])
        assert await get_user_global_balance(db, p1) == 1400.0

        # Step 2: P2 accepts duel
        msg2 = AsyncMock()
        msg2.from_user.id = p2
        msg2.chat.id = 111
        msg2.answer = AsyncMock()

        with patch("common.bot_helpers.get_pool", AsyncMock(return_value=db)):
            await accept_duel_logic(msg2, p1, "b", p2)

        final_total = (
            await get_user_global_balance(db, p1) +
            await get_user_global_balance(db, p2) +
            await get_abu_fund_total(db)
        )

        # Strict conservation of money: Delta == 0.0
        assert final_total == initial_total


# =============================================================================
# 11. COMBAT MODERATION BAIL ADVERSARIAL TESTS
# =============================================================================

class TestAdversarialCombatModerationBail:
    """Adversarial testing of combat moderation bail: zero balance or failed deduction must NEVER unmute."""

    @pytest.mark.asyncio
    async def test_zero_balance_cannot_exit_mute(self, isolated_test_db):
        """Muted victim with 0 shekels clicks 'Внести залог' -> strictly denied."""
        db = isolated_test_db
        victim_id = 95001
        session_id = create_combat_appeal_session(
            board_id="b", attacker_id=95002, target_id=victim_id, weapon_type="partyvan", duration_sec=300, chat_id=200, announcement_msg_id=100
        )
        sess = cme.active_combat_appeals[session_id]

        cb = AsyncMock()
        cb.from_user.id = victim_id
        cb.data = f"cbail:{session_id}"
        cb.answer = AsyncMock()

        with patch("combat_moderation_engine.get_pool", AsyncMock(return_value=db)), \
             patch("main.remove_regular_mute", new_callable=AsyncMock) as mock_unmute:
            await callback_combat_bail(cb)

            # Assert mute was NOT removed
            mock_unmute.assert_not_called()
            # Assert session is not bailed
            assert sess.is_bailed is False
            assert session_id in cme.active_combat_appeals
            # Assert alert sent to user
            cb.answer.assert_called_once()
            assert "Недостаточно шекелей" in cb.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_deduction_failure_aborts_unmute(self, isolated_test_db):
        """If deduct_user_global_balance returns False, bail MUST abort immediately."""
        db = isolated_test_db
        victim_id = 95003
        await add_user_global_balance(db, victim_id, "b", 1000.0)

        session_id = create_combat_appeal_session(
            board_id="b", attacker_id=95002, target_id=victim_id, weapon_type="partyvan", duration_sec=300, chat_id=200, announcement_msg_id=101
        )
        sess = cme.active_combat_appeals[session_id]

        cb = AsyncMock()
        cb.from_user.id = victim_id
        cb.data = f"cbail:{session_id}"
        cb.answer = AsyncMock()

        with patch("combat_moderation_engine.get_pool", AsyncMock(return_value=db)), \
             patch("main.deduct_user_global_balance", new_callable=AsyncMock, return_value=(False, 1000.0)), \
             patch("main.remove_regular_mute", new_callable=AsyncMock) as mock_unmute:
            await callback_combat_bail(cb)

            # Unmute MUST NOT be called
            mock_unmute.assert_not_called()
            assert sess.is_bailed is False
            cb.answer.assert_called_once()
            assert "Недостаточно шекелей" in cb.answer.call_args[0][0]
