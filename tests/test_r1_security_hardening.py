"""
Security Hardening Test Suite: R1 Red Team Hardening
Verifies fixes for:
1. Bot Token 307 leak elimination (safe streaming)
2. Russian Roulette shekel duplication (session bet locking & cashout security)
3. Stored BB-code XSS prevention ([btn=...])
4. File upload extension & MIME validation + safe disposition
5. IP spoofing protection in get_real_ip
6. TMA WebApp auth replay protection (auth_date validation)
"""

import hashlib
import hmac
import io
import os
import time
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import quote

import pytest
from fastapi import HTTPException
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from starlette.requests import Request
from starlette.responses import Response

from casino_engine import (
    active_roulette_sessions,
    play_russian_roulette_shot,
)
from site_tgach.image_processing import process_and_upload_image
from site_tgach.main import (
    app,
    format_post_text,
    get_real_ip,
    get_telegram_file,
)
from site_tgach.security import verify_telegram_webapp_data

# Initialize in-memory cache backend for test isolation if not yet initialized
try:
    FastAPICache.get_backend()
except Exception:
    FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache")


class DummyUploadFile:
    def __init__(self, filename: str, content_type: str, data: bytes):
        self.filename = filename
        self.content_type = content_type
        self.data = data
        self.file = io.BytesIO(data)
        self.size = len(data)

    async def seek(self, pos: int):
        self.file.seek(pos)

    async def read(self, n: int = -1):
        return self.file.read(n)


# ---------------------------------------------------------------------------
# 1. Bot Token 307 Leak Elimination Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_foreign_ip_media_streaming_does_not_leak_bot_token():
    """Non-RU clients must not receive HTTP 307 redirect containing bot token."""
    raw_headers = [(b"accept-language", b"en-US,en;q=0.9")]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/file/AgAC_token_leak_test",
        "query_string": b"",
        "headers": raw_headers,
        "client": ("198.51.100.55", 54321),
        "app": app,
    }
    req = Request(scope)
    req.state.lang = "en"
    req.state.t = lambda k, **kw: k

    with patch("site_tgach.main.get_country_by_ip", new_callable=AsyncMock) as mock_geo, \
         patch("site_tgach.main.get_file_mirrors", new_callable=AsyncMock) as mock_mirrors, \
         patch("site_tgach.main.get_cached_file_path", new_callable=AsyncMock) as mock_tg, \
         patch("site_tgach.main._proxy_protected_telegram_file", new_callable=AsyncMock) as mock_proxy:
        mock_geo.return_value = "US"
        mock_mirrors.return_value = {}
        mock_tg.return_value = ("photos/foreign_cat.jpg", "123456789:ABCdefGHIjklMNOpqrsTUVwxyz")
        mock_proxy.return_value = Response(content=b"streamed_image_bytes", media_type="image/jpeg", status_code=200)

        resp = await get_telegram_file(file_id="AgAC_token_leak_test", request=req)

        # Must NOT return HTTP 307
        assert resp.status_code == 200
        # Must NOT leak bot token in location header
        location = resp.headers.get("location", "")
        assert "api.telegram.org" not in location
        assert "123456789:ABCdefGHIjklMNOpqrsTUVwxyz" not in location
        mock_proxy.assert_awaited_once_with(
            "AgAC_token_leak_test", "photos/foreign_cat.jpg", "123456789:ABCdefGHIjklMNOpqrsTUVwxyz", None, req
        )


# ---------------------------------------------------------------------------
# 2. Russian Roulette Bet Locking & Cashout Tests
# ---------------------------------------------------------------------------

def test_russian_roulette_bet_locking_prevents_inflation():
    """play_russian_roulette_shot must retain initial bet across shots and not allow inflation."""
    test_user_id = 99887766
    active_roulette_sessions.pop(test_user_id, None)

    with patch("casino_engine.random.randint", return_value=2):  # safe shot
        survived, mult, streak, status = play_russian_roulette_shot(test_user_id, bet=100)
        assert survived is True
        assert streak == 1
        assert active_roulette_sessions[test_user_id]["bet"] == 100

        # Attempt to inflate bet to 1,000,000 on shot 2
        survived2, mult2, streak2, status2 = play_russian_roulette_shot(test_user_id, bet=1_000_000)
        assert survived2 is True
        assert streak2 == 2
        # Bet must remain locked to initial 100
        assert active_roulette_sessions[test_user_id]["bet"] == 100

    active_roulette_sessions.pop(test_user_id, None)


@pytest.mark.asyncio
async def test_russian_roulette_cashout_callback_extracts_session_bet():
    """cb_casino_handler must extract bet strictly from session and ignore forged callback numbers."""
    from main import cb_casino_handler

    test_user_id = 77665544
    active_roulette_sessions[test_user_id] = {
        "streak": 2,
        "bet": 100,
        "current_mult": 1.35,
        "last_shot": time.time(),
    }

    mock_callback = AsyncMock()
    mock_callback.from_user.id = test_user_id
    # Malicious client sends callback data claiming bet 999,999,999
    mock_callback.data = "cas:rr:cashout:999999999"
    mock_callback.message.chat.id = 12345
    mock_callback.bot = AsyncMock()

    mock_db = AsyncMock()

    with patch("main.get_pool", new_callable=AsyncMock, return_value=mock_db), \
         patch("main.add_user_global_balance", new_callable=AsyncMock) as mock_add_bal, \
         patch("main.record_user_transaction", new_callable=AsyncMock) as mock_rec_tx, \
         patch("main.calculate_win_tax", return_value=(0, 35)), \
         patch("banner_manager.send_banner_message", new_callable=AsyncMock):
        mock_add_bal.return_value = 1135

        await cb_casino_handler(mock_callback, board_id="b")

        # Payout added must be 135 (100 bet + 35 profit), NOT 999,999,999 * 1.35!
        mock_add_bal.assert_awaited_once_with(mock_db, test_user_id, "b", 135)
        mock_rec_tx.assert_awaited_once_with(mock_db, test_user_id, 35, 'casino', 'Куш в Русской Рулетке (x1.35)')

    assert test_user_id not in active_roulette_sessions


# ---------------------------------------------------------------------------
# 3. Stored BB-Code XSS Protection Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "malicious_bbcode",
    [
        "[btn=javascript:alert(1)]Click[/btn]",
        "[btn=java&#115;cript:alert(1)]Click[/btn]",
        "[btn=java&#x73;cript:alert(1)]Click[/btn]",
        "[btn=data:text/html,<script>alert(1)</script>]Click[/btn]",
        "[btn=vbscript:msgbox(1)]Click[/btn]",
        "[btn=//evil.com/payload]Click[/btn]",
        "[btn=/\\evil.com/payload]Click[/btn]",
        "[btn=blob:https://example.com/uuid]Click[/btn]",
        "[btn=file:///etc/passwd]Click[/btn]",
    ],
)
def test_bbcode_btn_xss_vectors_neutralized(malicious_bbcode):
    """Malicious protocols and obfuscated entities in [btn=...] must fallback to href="#"."""
    formatted = format_post_text(malicious_bbcode)
    assert 'href="#"' in formatted
    assert "javascript:" not in formatted.lower()
    assert "vbscript:" not in formatted.lower()
    assert "data:text" not in formatted.lower()


def test_bbcode_btn_safe_urls_allowed():
    """Legitimate http/https and relative paths must be accepted in [btn=...]."""
    safe_https = "[btn=https://example.com/safe]Link[/btn]"
    formatted_https = format_post_text(safe_https)
    assert 'href="https://example.com/safe"' in formatted_https

    safe_relative = "[btn=/b/res/12345]Thread[/btn]"
    formatted_relative = format_post_text(safe_relative)
    assert 'href="/b/res/12345"' in formatted_relative


# ---------------------------------------------------------------------------
# 4. File Upload Whitelist & Safe Disposition Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "filename,mime",
    [
        ("evil.exe", "application/x-msdownload"),
        ("evil.html", "text/html"),
        ("evil.svg", "image/svg+xml"),
        ("evil.js", "application/javascript"),
        ("evil.sh", "application/x-sh"),
        ("evil.php", "application/x-php"),
    ],
)
async def test_file_upload_rejects_dangerous_extensions_and_mimes(filename, mime):
    """process_and_upload_image must reject non-whitelisted extensions and dangerous MIME types."""
    dummy_file = DummyUploadFile(filename=filename, content_type=mime, data=b"malicious content")
    with pytest.raises(HTTPException) as exc_info:
        await process_and_upload_image(
            dummy_file,
            max_size_bytes=10 * 1024 * 1024,
            bot=MagicMock(),
            channel_id=12345,
        )
    assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# 5. IP Spoofing Protection Tests
# ---------------------------------------------------------------------------

def test_ip_spoofing_untrusted_client_ignores_proxy_headers():
    """Direct client connections must not be able to spoof IP via X-Forwarded-For or X-Real-IP."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [
            (b"x-forwarded-for", b"203.0.113.195, 10.0.0.1"),
            (b"x-real-ip", b"198.51.100.99"),
        ],
        "client": ("192.0.2.42", 50000),
    }
    req = Request(scope)
    # Untrusted client IP 192.0.2.42 should be returned, NOT spoofed headers
    assert get_real_ip(req) == "192.0.2.42"


def test_ip_spoofing_trusted_localhost_accepts_proxy_headers():
    """Connections from 127.0.0.1 (local reverse proxy) must trust forwarded headers."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [
            (b"x-forwarded-for", b"203.0.113.195, 127.0.0.1"),
            (b"x-real-ip", b"203.0.113.195"),
        ],
        "client": ("127.0.0.1", 50000),
    }
    req = Request(scope)
    assert get_real_ip(req) == "203.0.113.195"


# ---------------------------------------------------------------------------
# 6. TMA Auth Replay Attack Protection Tests
# ---------------------------------------------------------------------------

def _generate_valid_tma_init_data(bot_token: str, auth_date: int | None, user_id: int = 123456) -> str:
    """Helper to generate HMAC-SHA256 signed initData for Telegram Web App."""
    data_dict = {"user": f'{{"id":{user_id},"first_name":"Anon"}}'}
    if auth_date is not None:
        data_dict["auth_date"] = str(auth_date)

    sorted_items = sorted(data_dict.items())
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted_items)

    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    calc_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    encoded_parts = [f"{k}={quote(str(v))}" for k, v in data_dict.items()]
    encoded_parts.append(f"hash={calc_hash}")
    return "&".join(encoded_parts)


def test_tma_auth_replay_protection_valid_fresh_auth():
    """Fresh auth_date within 24 hours must be accepted."""
    test_token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
    now = int(time.time())
    fresh_init_data = _generate_valid_tma_init_data(test_token, auth_date=now - 300)

    with patch.dict(os.environ, {"MAIN_BOT_TOKEN": test_token}):
        parsed = verify_telegram_webapp_data(fresh_init_data)
        assert parsed is not None
        assert parsed["auth_date"] == str(now - 300)


def test_tma_auth_replay_protection_rejects_expired():
    """Expired auth_date older than 86,400s (24h) must be rejected."""
    test_token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
    now = int(time.time())
    expired_init_data = _generate_valid_tma_init_data(test_token, auth_date=now - 86401)

    with patch.dict(os.environ, {"MAIN_BOT_TOKEN": test_token}):
        parsed = verify_telegram_webapp_data(expired_init_data)
        assert parsed is None


def test_tma_auth_replay_protection_rejects_missing_auth_date():
    """initData missing auth_date must be rejected."""
    test_token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
    missing_auth_date_data = _generate_valid_tma_init_data(test_token, auth_date=None)

    with patch.dict(os.environ, {"MAIN_BOT_TOKEN": test_token}):
        parsed = verify_telegram_webapp_data(missing_auth_date_data)
        assert parsed is None


def test_tma_auth_replay_protection_rejects_future_drift():
    """auth_date more than 60 seconds in future must be rejected."""
    test_token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
    now = int(time.time())
    future_init_data = _generate_valid_tma_init_data(test_token, auth_date=now + 120)

    with patch.dict(os.environ, {"MAIN_BOT_TOKEN": test_token}):
        parsed = verify_telegram_webapp_data(future_init_data)
        assert parsed is None
