import asyncio
import io
import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from fastapi import HTTPException
from fastapi.testclient import TestClient
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend

from site_tgach.main import (
    app,
    _proxy_protected_telegram_file,
    _proxy_external_url,
    get_telegram_file,
    format_post_text,
    format_poll_for_html,
    PooledConnectionContext,
    get_readonly_db_connection,
    custom_500_handler,
    templates,
)

try:
    FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache-redteam")
except Exception:
    pass


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def mock_external_deps(isolated_test_db):
    """Provide isolated SQLite database and mock external network lookups."""
    with patch("site_tgach.main.get_country_by_ip", new_callable=AsyncMock) as mock_country, \
         patch("site_tgach.main.get_system_setting", new_callable=AsyncMock) as mock_setting:
        mock_country.return_value = "RU"
        mock_setting.return_value = "false"
        yield


# ==============================================================================
# 1. STREAMING PROXY & TIMEOUT / PROTOCOL RESILIENCE
# ==============================================================================
class TestStreamingProxyResilience:
    """Tests resilience of _proxy_protected_telegram_file and _proxy_external_url against timeouts and premature drops."""

    @pytest.mark.asyncio
    async def test_proxy_telegram_status_200_omits_content_length_for_chunked(self):
        """200 OK responses must omit Content-Length so h11 chunked encoding prevents LocalProtocolError on pause/abort."""
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.headers = {
            "Content-Type": "image/jpeg",
            "Content-Length": "1234567",
            "Accept-Ranges": "bytes",
            "ETag": '"abcdef"',
        }

        async def fake_iter(chunk_size):
            yield b"part1"
            yield b"part2"

        mock_resp.content = MagicMock()
        mock_resp.content.iter_chunked = fake_iter
        mock_session = AsyncMock()
        mock_session.get.return_value = mock_resp

        with patch("site_tgach.main._get_shared_aiohttp_session", return_value=mock_session), \
             patch("site_tgach.main.add_to_mirror_queue", new_callable=AsyncMock):
            res = await _proxy_protected_telegram_file("AgAC123", "photos/file.jpg", "test_token")
            assert isinstance(res, StreamingResponse)
            assert res.status_code == 200
            assert "content-length" not in res.headers
            assert res.headers["accept-ranges"] == "bytes"

    @pytest.mark.asyncio
    async def test_proxy_telegram_status_206_preserves_content_length_and_range(self):
        """206 Partial Content responses require Content-Range and Content-Length per RFC 7233."""
        mock_resp = AsyncMock()
        mock_resp.status = 206
        mock_resp.headers = {
            "Content-Type": "video/mp4",
            "Content-Length": "1000",
            "Content-Range": "bytes 0-999/5000",
            "Accept-Ranges": "bytes",
        }

        async def fake_iter(chunk_size):
            yield b"video_bytes"

        mock_resp.content = MagicMock()
        mock_resp.content.iter_chunked = fake_iter
        mock_session = AsyncMock()
        mock_session.get.return_value = mock_resp

        with patch("site_tgach.main._get_shared_aiohttp_session", return_value=mock_session), \
             patch("site_tgach.main.add_to_mirror_queue", new_callable=AsyncMock):
            res = await _proxy_protected_telegram_file("BAAC123", "videos/file.mp4", "test_token")
            assert isinstance(res, StreamingResponse)
            assert res.status_code == 206
            assert res.headers["content-length"] == "1000"
            assert res.headers["content-range"] == "bytes 0-999/5000"

    @pytest.mark.asyncio
    async def test_proxy_stream_interruption_does_not_raise(self):
        """If upstream times out or connection resets mid-stream, body_iter must catch it gracefully."""
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.headers = {"Content-Type": "image/jpeg"}

        async def broken_iter(chunk_size):
            yield b"start"
            raise asyncio.TimeoutError("Upstream socket stalled")

        mock_resp.content = MagicMock()
        mock_resp.content.iter_chunked = broken_iter
        mock_resp.release = MagicMock()
        mock_session = AsyncMock()
        mock_session.get.return_value = mock_resp

        with patch("site_tgach.main._get_shared_aiohttp_session", return_value=mock_session), \
             patch("site_tgach.main.add_to_mirror_queue", new_callable=AsyncMock):
            res = await _proxy_protected_telegram_file("AgAC123", "photos/file.jpg", "test_token")
            chunks = []
            async for chunk in res.body_iterator:
                chunks.append(chunk)
            assert chunks == [b"start"]
            assert mock_resp.release.called

    @pytest.mark.asyncio
    async def test_custom_500_handler_catches_client_abort_cleanly(self):
        """Protocol/client disconnection errors must return 499/200 without raising an unhandled 500 error."""
        scope = {"type": "http", "method": "GET", "path": "/files/BAAC123", "query_string": b"", "headers": []}
        req = Request(scope)

        class LocalProtocolError(Exception):
            pass

        exc = LocalProtocolError("Too little data for declared Content-Length")
        resp = await custom_500_handler(req, exc)
        assert resp.status_code in (200, 499)


# ==============================================================================
# 2. PATH TRAVERSAL & DOMAIN REDIRECT DEFENSE
# ==============================================================================
class TestPathTraversalAndRedirectSecurity:
    """Validates prevention of path traversal attacks and arbitrary external redirects."""

    @pytest.mark.asyncio
    async def test_get_telegram_file_directory_traversal_blocked(self):
        scope = {"type": "http", "method": "GET", "path": "/files/../../etc/passwd", "query_string": b"", "headers": []}
        req = Request(scope)
        with pytest.raises(HTTPException) as exc_info:
            await get_telegram_file("../../etc/passwd", req)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_telegram_file_untrusted_redirect_blocked(self):
        scope = {"type": "http", "method": "GET", "path": "/files/https://evil.com/malware.exe", "query_string": b"", "headers": []}
        req = Request(scope)
        with pytest.raises(HTTPException) as exc_info:
            await get_telegram_file("https://evil.com/malware.exe", req)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_get_telegram_file_trusted_redirect_allowed(self):
        scope = {"type": "http", "method": "GET", "path": "/files/https://files.catbox.moe/abc123.jpg", "query_string": b"", "headers": []}
        req = Request(scope)
        res = await get_telegram_file("https://files.catbox.moe/abc123.jpg", req)
        assert res.status_code == 301
        assert res.headers["location"] == "https://files.catbox.moe/abc123.jpg"

    @pytest.mark.asyncio
    async def test_get_telegram_file_empty_thumb_path_does_not_crash(self):
        """Non-alphanumeric file_id (e.g. '---___') must not cause open('', 'wb') FileNotFoundError."""
        scope = {"type": "http", "method": "GET", "path": "/thumb/---___", "query_string": b"", "headers": []}
        req = Request(scope)
        with patch("site_tgach.main.get_cached_file_path", return_value=("thumb.jpg", "tok")), \
             patch("site_tgach.main._get_shared_aiohttp_session") as mock_sess:
            mock_sess.return_value.get.side_effect = Exception("Failed")
            with pytest.raises(HTTPException) as exc_info:
                await get_telegram_file("---___", req)
            assert exc_info.value.status_code == 404


# ==============================================================================
# 3. RATE LIMITING & DOS DEFENSE
# ==============================================================================
class TestRateLimitingAndDoSDefenses:
    """Tests rate limits and payload size protections on sensitive site endpoints."""

    def test_search_endpoint_query_clamped(self, client):
        long_query = "A" * 500
        with patch("site_tgach.main.search_posts", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = []
            res = client.get(f"/search?query={long_query}")
            assert res.status_code in (200, 429)
            if res.status_code == 200:
                assert mock_search.called
                called_query = mock_search.call_args[0][0]
                assert len(called_query) <= 200

    def test_makaba_posting_comment_length_limit(self, client):
        huge_comment = "B" * 20000
        res = client.post(
            "/makaba/posting.fcgi",
            data={
                "task": "post",
                "board": "b",
                "thread": "0",
                "comment": huge_comment,
            },
        )
        assert res.status_code == 400
        data = res.json()
        assert "too long" in data.get("Error", "").lower()

    def test_create_post_text_length_limit(self, client):
        huge_text = "C" * 20000
        res = client.post(
            "/api/post/b",
            data={
                "post_mode": "new_thread",
                "text": huge_text,
            },
        )
        assert res.status_code == 400
        assert "too long" in res.json().get("detail", "").lower()

    def test_favourites_endpoint_clamps_thread_ids(self, client):
        """Sending 1000 IDs must not crash SQLite with too many variables; must be clamped to 100."""
        payload = {"thread_ids": [str(i) for i in range(1000)]}
        res = client.post("/api/favourites", json=payload)
        assert res.status_code in (200, 429)
        assert isinstance(res.json(), list)

    def test_my_replies_list_clamps_negative_page(self, client):
        """Negative page numbers must be clamped to 0 to prevent negative SQL offsets."""
        with patch("site_tgach.main.get_user_replies", new_callable=AsyncMock) as mock_replies:
            mock_replies.return_value = []
            res = client.get("/api/my/replies/list?page=-5")
            assert res.status_code in (200, 429)
            if res.status_code == 200:
                assert mock_replies.called
                _, limit, offset = mock_replies.call_args[0]
                assert offset >= 0


# ==============================================================================
# 4. DATABASE CONCURRENCY & READ-ONLY FALLBACK
# ==============================================================================
class TestDatabaseReadOnlyFallback:
    """Tests automatic read-only SQLite fallback when primary pool connection fails."""

    @pytest.mark.asyncio
    async def test_pooled_connection_context_ro_fallback_on_primary_failure(self):
        with patch("site_tgach.main.get_pool", side_effect=Exception("Database lock acquisition timeout")):
            ctx = PooledConnectionContext()
            async with ctx as conn:
                assert conn is not None
                assert ctx._is_ro_fallback is True
                async with conn.execute("SELECT 1") as cursor:
                    row = await cursor.fetchone()
                    assert row[0] == 1

                # Write operation must fail on read-only fallback
                with pytest.raises(Exception):
                    await conn.execute("CREATE TABLE _ro_test_tbl (x INT)")

    @pytest.mark.asyncio
    async def test_get_readonly_db_connection_context(self):
        ctx = get_readonly_db_connection()
        async with ctx as conn:
            assert conn is not None
            async with conn.execute("SELECT 1") as cursor:
                row = await cursor.fetchone()
                assert row[0] == 1


# ==============================================================================
# 5. XSS & SSR RENDERING SECURITY
# ==============================================================================
class TestXSSAndSSRDefenses:
    """Tests that user-supplied content is safely sanitized and neutralized across SSR templates."""

    def test_format_post_text_disarms_javascript_urls(self):
        dirty_btn = '[btn=javascript:alert("XSS")]Click me[/btn]'
        cleaned_btn = format_post_text(dirty_btn)
        assert 'href="#"' in cleaned_btn or "javascript:" not in cleaned_btn.lower()

        dirty_html = '<a href="javascript:alert(1)">Click</a>'
        cleaned_html = format_post_text(dirty_html)
        assert "javascript:" not in cleaned_html.lower()

    def test_format_post_text_disarms_data_urls(self):
        dirty_btn = '[btn=data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==]Test[/btn]'
        cleaned_btn = format_post_text(dirty_btn)
        assert 'href="#"' in cleaned_btn or "data:text/html" not in cleaned_btn.lower()

        dirty_html = '<a href="data:text/html;base64,abc">Click</a>'
        cleaned_html = format_post_text(dirty_html)
        assert "data:text/html" not in cleaned_html.lower()

    def test_format_post_text_escapes_html_tags(self):
        payload = "<script>alert(1)</script><img src=x onerror=alert(2)>"
        cleaned = format_post_text(payload)
        assert "<script>" not in cleaned
        assert "<img src=x" not in cleaned
        assert "&lt;script&gt;" in cleaned or "&lt;img" in cleaned

    def test_format_poll_for_html_escapes_xss(self):
        poll = {
            "question": "<script>alert('poll')</script>",
            "options": ["<b>Opt1</b>", "<img src=x onerror=alert(1)>"],
            "votes": {"0": [1]},
        }
        rendered = format_poll_for_html(poll)
        assert "<script>" not in rendered
        assert "<img src=x" not in rendered
        assert "&lt;script&gt;" in rendered

    def test_catalog_template_striptags_not_marked_safe(self):
        """Verifies catalog.jinja2 uses striptags without preceding | safe, allowing autoescape."""
        template_text = open(r"C:\dev\dvachbot\site_tgach\templates\catalog.jinja2", "r", encoding="utf-8").read()
        assert "| safe | striptags" not in template_text
