import hashlib
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.requests import Request
from starlette.responses import Response
from starlette.websockets import WebSocket
from fastapi import HTTPException
from PIL import Image
import io

from site_tgach.security import (
    is_safe_url,
    verify_pow,
    check_ddos,
    generate_challenge_str,
    cleanup_ddos_history,
    POW_CACHE,
    IP_BAN_LIST as SEC_IP_BAN_LIST,
    REQUEST_HISTORY,
    ALLOWED_IMPORT_DOMAINS,
)
from site_tgach.image_processing import (
    is_valid_media_magic,
    process_and_upload_image,
)
from site_tgach.main import (
    get_real_ip,
    country_cookie_middleware,
    ConnectionManager,
)
from site_tgach.importer import ThreadImporter, MemoryUploadFile
from site_tgach.vision import prepare_image_for_groq, prepare_image_for_analysis


class TestWave3SSRFDefense:
    """Rigorous tests for SSRF prevention, including IPv4-mapped IPv6 and port filtering."""

    def test_ssrf_disallowed_hostnames_and_ips(self):
        assert not is_safe_url("http://localhost/")
        assert not is_safe_url("http://127.0.0.1:8080/admin")
        assert not is_safe_url("http://169.254.169.254/latest/meta-data/")
        assert not is_safe_url("http://169.254.170.2/v2/metadata")
        assert not is_safe_url("http://metadata.google.internal/computeMetadata/v1/")
        assert not is_safe_url("http://metadata/")
        assert not is_safe_url("http://instance-data/")
        assert not is_safe_url("http://[::1]/")

    def test_ssrf_ipv4_mapped_ipv6(self):
        # [::ffff:127.0.0.1] and [::ffff:169.254.169.254]
        assert not is_safe_url("http://[::ffff:127.0.0.1]/")
        assert not is_safe_url("http://[::ffff:169.254.169.254]/")
        assert not is_safe_url("http://[::ffff:10.0.0.1]/")

    def test_ssrf_port_filtering(self):
        # Allowed ports: 80, 443, 8080, 8443
        assert is_safe_url("https://2ch.hk:443/b/res/1.json", allowed_domains=ALLOWED_IMPORT_DOMAINS)
        assert is_safe_url("http://2ch.hk:80/b/res/1.json", allowed_domains=ALLOWED_IMPORT_DOMAINS)
        # Dangerous internal ports must be blocked even if domain looks valid
        assert not is_safe_url("http://2ch.hk:6379/", allowed_domains=ALLOWED_IMPORT_DOMAINS)  # Redis
        assert not is_safe_url("http://2ch.hk:11211/", allowed_domains=ALLOWED_IMPORT_DOMAINS) # Memcached
        assert not is_safe_url("http://2ch.hk:22/", allowed_domains=ALLOWED_IMPORT_DOMAINS)    # SSH
        assert not is_safe_url("http://2ch.hk:25/", allowed_domains=ALLOWED_IMPORT_DOMAINS)    # SMTP

    def test_ssrf_integer_and_hex_encodings(self):
        assert not is_safe_url("http://2130706433/")
        assert not is_safe_url("http://2852039166/")
        assert not is_safe_url("http://0x7f000001/")

    def test_ssrf_allowed_domains(self):
        assert is_safe_url("https://2ch.hk/b/res/123.json", allowed_domains=ALLOWED_IMPORT_DOMAINS)
        assert is_safe_url("https://a.4cdn.org/b/thread/123.json", allowed_domains=ALLOWED_IMPORT_DOMAINS)
        assert not is_safe_url("https://evil-2ch.hk/fake.json", allowed_domains=ALLOWED_IMPORT_DOMAINS)
        assert not is_safe_url("https://evil.org/test.json", allowed_domains=ALLOWED_IMPORT_DOMAINS)


class TestWave3PoWIntegrity:
    """Tests for PoW difficulty validation, bypass protection, and replay prevention."""

    def test_pow_negative_or_invalid_difficulty_rejected(self):
        challenge = generate_challenge_str()
        # Negative difficulty must be rejected, NOT treated as empty prefix match
        assert not verify_pow(challenge, "any_nonce", difficulty=-1)
        assert not verify_pow(challenge, "any_nonce", difficulty=-5)
        # Non-integer difficulty
        assert not verify_pow(challenge, "any_nonce", difficulty="invalid")
        assert not verify_pow(challenge, "any_nonce", difficulty=None)

    def test_pow_zero_difficulty(self):
        # Difficulty 0 is permitted if explicitly passed
        challenge = generate_challenge_str()
        assert verify_pow(challenge, "nonce", difficulty=0)

    def test_pow_valid_solution_consumed(self):
        challenge = generate_challenge_str()
        diff = 2
        target = "0" * diff
        nonce = None
        for i in range(100000):
            res = hashlib.sha256(f"{challenge}{i}".encode("utf-8")).hexdigest()
            if res.startswith(target):
                nonce = str(i)
                break
        assert nonce is not None
        # First verification succeeds
        assert verify_pow(challenge, nonce, difficulty=diff)
        # Replay must fail because challenge was consumed from cache
        assert not verify_pow(challenge, nonce, difficulty=diff)


class TestWave3IPSpoofingAndWebSocket:
    """Tests for X-Forwarded-For right-to-left traversal, Cloudflare CF-Connecting-IP, and WS rate limits."""

    def test_get_real_ip_from_untrusted_client_ignores_spoofed_headers(self):
        # When request comes directly from untrusted public IP (e.g. 93.184.216.34)
        scope = {
            "type": "http",
            "client": ("93.184.216.34", 12345),
            "headers": [
                (b"x-forwarded-for", b"8.8.8.8, 1.1.1.1"),
                (b"x-real-ip", b"8.8.8.8"),
                (b"cf-connecting-ip", b"8.8.8.8"),
            ],
        }
        req = Request(scope)
        # Must return the direct client socket IP, ignoring spoofed headers
        assert get_real_ip(req) == "93.184.216.34"

    def test_get_real_ip_from_trusted_proxy_handles_cf_and_xff(self):
        # 1. CF-Connecting-IP takes precedence from trusted reverse proxy (e.g. 127.0.0.1)
        scope_cf = {
            "type": "http",
            "client": ("127.0.0.1", 54321),
            "headers": [
                (b"cf-connecting-ip", b"93.184.216.34"),
                (b"x-forwarded-for", b"8.8.8.8, 93.184.216.34"),
            ],
        }
        assert get_real_ip(Request(scope_cf)) == "93.184.216.34"

        # 2. X-Forwarded-For traversed right-to-left prevents attacker from spoofing via leftmost value
        scope_xff = {
            "type": "http",
            "client": ("127.0.0.1", 54321),
            "headers": [
                # Attacker sent X-Forwarded-For: 8.8.8.8, proxy appended attacker's real IP 178.62.204.1
                (b"x-forwarded-for", b"8.8.8.8, 178.62.204.1"),
            ],
        }
        assert get_real_ip(Request(scope_xff)) == "178.62.204.1"

    @pytest.mark.asyncio
    async def test_websocket_connection_manager_ip_counts_pruning(self):
        manager = ConnectionManager()
        # Mock WebSocket from trusted proxy with right-to-left XFF
        scope_ws = {
            "type": "websocket",
            "client": ("127.0.0.1", 12345),
            "headers": [
                (b"x-forwarded-for", b"9.9.9.9, 178.62.204.1"),
            ],
        }
        ws = WebSocket(scope_ws, receive=AsyncMock(), send=AsyncMock())
        ws.accept = AsyncMock()
        ws.close = AsyncMock()

        await manager.connect(ws, board_id="b", mode="threads", stream="ru")
        assert manager.ip_counts["178.62.204.1"] == 1

        # Disconnecting must decrement and prune the key to 0 so it doesn't leak in memory
        manager.disconnect(ws, board_id="b", mode="threads", stream="ru")
        assert "178.62.204.1" not in manager.ip_counts


class TestWave3DDoSRateLimiterMemoryLeaks:
    """Tests that IP_BAN_LIST and REQUEST_HISTORY are properly cleaned up without memory leaks."""

    def setup_method(self):
        REQUEST_HISTORY.clear()
        SEC_IP_BAN_LIST.clear()
        POW_CACHE.clear()

    def test_cleanup_ddos_history_prunes_expired_entries(self):
        now = time.time()
        # Add expired and active entries
        REQUEST_HISTORY["198.51.100.1"] = [1, now - 100]
        REQUEST_HISTORY["198.51.100.2"] = [1, now]
        SEC_IP_BAN_LIST["198.51.100.3"] = now - 50
        SEC_IP_BAN_LIST["198.51.100.4"] = now + 50
        POW_CACHE["expired_ch"] = now - 10
        POW_CACHE["active_ch"] = now + 100

        cleanup_ddos_history()

        assert "198.51.100.1" not in REQUEST_HISTORY
        assert "198.51.100.2" in REQUEST_HISTORY
        assert "198.51.100.3" not in SEC_IP_BAN_LIST
        assert "198.51.100.4" in SEC_IP_BAN_LIST
        assert "expired_ch" not in POW_CACHE
        assert "active_ch" in POW_CACHE

    def test_check_ddos_cleans_expired_bans(self):
        test_ip = "198.51.100.77"
        # Manually inject expired ban
        SEC_IP_BAN_LIST[test_ip] = time.time() - 10
        # check_ddos should see ban has expired and remove it
        banned = check_ddos(test_ip)
        assert not banned
        assert test_ip not in SEC_IP_BAN_LIST


class TestWave3MediaSecurityAndDecompressionBomb:
    """Tests for MIME magic-byte verification, decompression bomb limits, and safe media downloading."""

    def test_valid_media_magic_bytes(self):
        # JPEG: \xff\xd8\xff
        assert is_valid_media_magic(b"\xff\xd8\xff\xe0\x00\x10JFIF")
        # PNG: \x89PNG\r\n\x1a\n
        assert is_valid_media_magic(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
        # GIF: GIF89a
        assert is_valid_media_magic(b"GIF89a\x01\x00\x01\x00")
        # WEBP: RIFF....WEBP
        assert is_valid_media_magic(b"RIFF\x24\x00\x00\x00WEBPVP8 ")
        # MP4: ....ftyp
        assert is_valid_media_magic(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00")

    def test_disallowed_formats_and_payloads(self):
        # HTML disguised as image
        assert not is_valid_media_magic(b"<!DOCTYPE html><html><script>alert(1)</script></html>")
        # SVG with script/XXE
        assert not is_valid_media_magic(b"<svg xmlns=\"http://www.w3.org/2000/svg\"><script>alert(1)</script></svg>")
        # XML payload
        assert not is_valid_media_magic(b"<?xml version=\"1.0\"?><!ENTITY xxe SYSTEM \"file:///etc/passwd\">")
        # Executable binary (PE / MZ)
        assert not is_valid_media_magic(b"MZ\x90\x00\x03\x00\x00\x00")
        # Linux ELF binary
        assert not is_valid_media_magic(b"\x7fELF\x02\x01\x01\x00")
        # ZIP archive
        assert not is_valid_media_magic(b"PK\x03\x04\x14\x00\x00\x00")

    @pytest.mark.asyncio
    async def test_process_and_upload_image_rejects_disallowed_magic(self):
        fake_file = MemoryUploadFile(
            file=io.BytesIO(b"<script>alert('pwned')</script>"),
            filename="image.png",
            content_type="image/png",
        )
        with pytest.raises(HTTPException) as exc_info:
            await process_and_upload_image(fake_file, max_size_bytes=10 * 1024 * 1024, bot=None, channel_id=123)
        assert exc_info.value.status_code == 400
        assert "Corrupted or disallowed" in exc_info.value.detail

    def test_prepare_image_for_groq_catches_decompression_bomb(self):
        with patch("PIL.Image.open") as mock_open:
            mock_open.side_effect = Image.DecompressionBombError("Image size exceeds limit")
            res, err = prepare_image_for_groq(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
            assert res is None
            assert "Decompression bomb" in err

    @pytest.mark.asyncio
    async def test_prepare_image_for_analysis_catches_decompression_bomb(self):
        with patch("PIL.Image.open") as mock_open:
            mock_open.side_effect = Image.DecompressionBombError("Image size exceeds limit")
            res, err = await prepare_image_for_analysis("fake_path.jpg")
            assert res is None
            assert "Decompression bomb" in err


class TestWave3ImporterLifecycleAndSafeRequest:
    """Tests for ThreadImporter ThreadPool executor lifecycle and streaming size checks."""

    @pytest.mark.asyncio
    async def test_normalize_html_reinitializes_executor_after_close(self):
        importer = ThreadImporter(bot=None, file_storage_channel_id=123)
        res1 = await importer.normalize_html("двач test")
        assert "тгач test" in res1

        # Simulate importer close or thread shutdown
        importer.close()

        # Calling normalize_html again must NOT raise RuntimeError: cannot schedule new futures after shutdown
        res2 = await importer.normalize_html("двачер test")
        assert "тгачер test" in res2

    @pytest.mark.asyncio
    async def test_importer_safe_request_blocks_oversized_downloads(self):
        importer = ThreadImporter(bot=None, file_storage_channel_id=123)

        class MockStreamResponse:
            status_code = 200
            headers = {"content-length": str(100 * 1024 * 1024), "content-type": "image/jpeg"}  # 100 MB > 50 MB limit
            request = MagicMock()
            async def aiter_bytes(self):
                yield b"\x00" * 1024

        class MockClient:
            def stream(self, *args, **kwargs):
                class StreamCtx:
                    async def __aenter__(self):
                        return MockStreamResponse()
                    async def __aexit__(self, *args):
                        pass
                return StreamCtx()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value = MockClient()
            res = await importer._safe_request("https://2ch.hk/b/src/oversized.jpg")
            assert res is None


class TestWave3Invariants:
    """Critical system invariants."""

    @pytest.mark.asyncio
    async def test_user_country_cookie_httponly_false_preserved(self):
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/b/",
            "headers": [(b"host", b"testserver")],
        }
        request = Request(scope)
        call_next = AsyncMock(return_value=Response(b"ok"))

        with patch("site_tgach.main.get_real_ip", return_value="95.161.222.1"), \
             patch("site_tgach.main.get_country_by_ip", return_value="RU"):
            response = await country_cookie_middleware(request, call_next)

        set_cookie = response.headers.get("set-cookie", "")
        assert "user_country=RU" in set_cookie
        # Cookie MUST remain accessible to frontend JavaScript VpnManager
        assert "HttpOnly" not in set_cookie
