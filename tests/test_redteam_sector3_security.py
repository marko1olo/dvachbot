import hashlib
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.requests import Request
from starlette.responses import Response
from fastapi import HTTPException

from site_tgach.security import (
    is_safe_url,
    verify_pow,
    check_ddos,
    generate_challenge_str,
    POW_CACHE,
    IP_BAN_LIST as SEC_IP_BAN_LIST,
    REQUEST_HISTORY,
    ALLOWED_IMPORT_DOMAINS,
)
from site_tgach.admin_config import IP_BAN_LIST as ADMIN_IP_BAN_LIST
from site_tgach.main import (
    country_cookie_middleware,
    _proxy_external_url,
)
from site_tgach.importer import ThreadImporter


class TestRedteamSector3SSRF:
    """Security tests for SSRF prevention in Sector 3."""

    def test_ssrf_disallowed_hostnames_and_ips(self):
        assert not is_safe_url("http://localhost/")
        assert not is_safe_url("http://127.0.0.1/admin")
        assert not is_safe_url("http://169.254.169.254/latest/meta-data/")
        assert not is_safe_url("http://metadata.google.internal/computeMetadata/v1/")
        assert not is_safe_url("http://metadata/")
        assert not is_safe_url("http://instance-data/")
        assert not is_safe_url("http://[::1]/")

    def test_ssrf_integer_and_hex_encoded_ips(self):
        # 2130706433 is 127.0.0.1
        assert not is_safe_url("http://2130706433/")
        # 2852039166 is 169.254.169.254 (Cloud metadata)
        assert not is_safe_url("http://2852039166/")
        # Hex representation 0x7f000001 is 127.0.0.1
        assert not is_safe_url("http://0x7f000001/")

    def test_ssrf_private_and_link_local_subnets(self):
        assert not is_safe_url("http://10.0.0.1/internal")
        assert not is_safe_url("http://172.16.0.1/internal")
        assert not is_safe_url("http://192.168.1.1/router")
        assert not is_safe_url("http://0.0.0.0/")

    def test_ssrf_allowed_domains_enforcement(self):
        assert is_safe_url("https://2ch.hk/b/res/123.json", allowed_domains=ALLOWED_IMPORT_DOMAINS)
        assert is_safe_url("https://a.4cdn.org/b/thread/123.json", allowed_domains=ALLOWED_IMPORT_DOMAINS)
        assert not is_safe_url("https://evil-attacker.com/malicious.json", allowed_domains=ALLOWED_IMPORT_DOMAINS)
        assert not is_safe_url("https://attacker2ch.hk/fake.json", allowed_domains=ALLOWED_IMPORT_DOMAINS)

    @pytest.mark.asyncio
    async def test_proxy_external_url_blocks_ssrf(self):
        with pytest.raises(HTTPException) as exc_info:
            await _proxy_external_url("http://169.254.169.254/latest/meta-data/")
        assert exc_info.value.status_code == 400


class TestRedteamSector3PoW:
    """Security tests for Proof-of-Work verification and replay attack protection."""

    def test_pow_valid_solution(self):
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
        # Must verify successfully
        assert verify_pow(challenge, nonce, difficulty=diff)
        # Replay must fail because challenge was consumed
        assert not verify_pow(challenge, nonce, difficulty=diff)

    def test_pow_expired_challenge(self):
        challenge = "test_expired_challenge"
        # Set expiry in the past
        POW_CACHE[challenge] = time.time() - 10
        assert not verify_pow(challenge, "1234", difficulty=2)
        assert challenge not in POW_CACHE

    def test_pow_invalid_inputs(self):
        assert not verify_pow("", "123")
        assert not verify_pow("fake_challenge", "")
        assert not verify_pow(None, "123")
        assert not verify_pow("challenge", None)
        assert not verify_pow(12345, "123")


class TestRedteamSector3DDoSAndBan:
    """Security tests for DDoS protection and IP Ban consistency."""

    def setup_method(self):
        REQUEST_HISTORY.clear()
        SEC_IP_BAN_LIST.clear()

    def test_check_ddos_invalid_input(self):
        assert not check_ddos(None)
        assert not check_ddos("")
        assert not check_ddos("   ")

    def test_check_ddos_ban_threshold(self):
        test_ip = "198.51.100.42"
        for _ in range(200):
            check_ddos(test_ip)
        # 201st request exceeds MAX_REQUESTS_PER_WINDOW and triggers ban
        is_banned = check_ddos(test_ip)
        assert is_banned
        assert test_ip in SEC_IP_BAN_LIST

    def test_check_ddos_canonicalizes_ipv6(self):
        # Unexpanded and expanded IPv6 format of same address
        ip_v6_compressed = "2001:db8::1"
        ip_v6_expanded = "2001:0db8:0000:0000:0000:0000:0000:0001"
        SEC_IP_BAN_LIST[ip_v6_compressed] = time.time() + 60
        # Check should recognize it is banned regardless of format variation
        assert check_ddos(ip_v6_expanded)

    def test_ip_ban_list_shared_singleton(self):
        # admin_config.IP_BAN_LIST and security.IP_BAN_LIST must be the exact same object
        ADMIN_IP_BAN_LIST["203.0.113.99"] = 123456.0
        assert "203.0113.99" not in SEC_IP_BAN_LIST or SEC_IP_BAN_LIST.get("203.0.113.99") == 123456.0
        assert SEC_IP_BAN_LIST is ADMIN_IP_BAN_LIST


class TestRedteamSector3UserCountryCookie:
    """Security and compliance test: user_country cookie MUST have httponly=False."""

    @pytest.mark.asyncio
    async def test_user_country_cookie_httponly_false(self):
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
        # CRITICAL LAW: Cookie MUST NOT have HttpOnly flag so VpnManager in JS can read it
        assert "HttpOnly" not in set_cookie
        assert "samesite=lax" in set_cookie.lower()


class TestRedteamSector3Importer:
    """Tests for 2ch importer robustness, timeouts, and DLQ handling."""

    @pytest.mark.asyncio
    async def test_safe_request_handles_none_client_gracefully(self):
        importer = ThreadImporter(bot=None, file_storage_channel_id=123)
        importer.client = None
        # Must not raise AttributeError when importer.client is None
        res = await importer._safe_request("https://invalid-ssrf-check.internal/test")
        assert res is None

    @pytest.mark.asyncio
    async def test_fetch_json_non_json_response_raises_value_error(self):
        importer = ThreadImporter(bot=None, file_storage_channel_id=123)

        class MockStreamResponse:
            status_code = 200
            async def aiter_bytes(self):
                yield b"<html><body>Cloudflare Block</body></html>"

        class MockClient:
            def stream(self, *args, **kwargs):
                class StreamCtx:
                    async def __aenter__(self):
                        return MockStreamResponse()
                    async def __aexit__(self, *args):
                        pass
                return StreamCtx()

        importer.client = MockClient()
        with pytest.raises(ValueError) as exc_info:
            await importer.fetch_json("https://2ch.hk/b/res/1.json")
        assert "non-JSON response" in str(exc_info.value)
