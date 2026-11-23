"""
Tests for Security Traps (Well-Known & Crawlers Whitelisting) and SSR Accessibility.

Verifies:
1. RFC service paths (/.well-known/apple-app-site-association, assetlinks.json, security.txt, robots.txt, sitemap.xml)
   and legitimate crawlers NEVER trigger bot-traps or IP penalties.
2. SSR HTML pages (board.jinja2, thread.jinja2, overboard.jinja2, catalog.jinja2) render complete post content,
   titles, dates, anon names, and images without JavaScript, providing full readability for curl/lynx/Tor users.
3. Malicious vulnerability scanners (/admin, /.git, /phpmyadmin, etc.) are strictly caught and trapped.
"""

import time
import pytest
from unittest.mock import AsyncMock, patch
from pathlib import Path
from starlette.requests import Request
from starlette.datastructures import Headers
from fastapi import HTTPException
from jinja2 import Environment, FileSystemLoader

from site_tgach.security import (
    WHITELISTED_WELL_KNOWN,
    LEGITIMATE_CRAWLER_USER_AGENTS,
    is_whitelisted_well_known,
    is_legitimate_crawler,
    should_trap_bot,
)
from site_tgach.main import (
    custom_404_handler,
    is_bot_by_headers,
    IP_TROLL_CONFIG,
    BOT_VIOLATIONS,
)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "site_tgach" / "templates"


def make_dummy_request(
    path: str = "/b/",
    method: str = "GET",
    client_ip: str = "203.0.113.195",
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    headers: dict | None = None,
) -> Request:
    raw_headers = [
        (b"host", b"tgach.top"),
        (b"user-agent", user_agent.encode("utf-8")),
        (b"x-forwarded-for", client_ip.encode("utf-8")),
    ]
    if headers:
        for k, v in headers.items():
            raw_headers.append((k.lower().encode("utf-8"), v.encode("utf-8")))

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "headers": raw_headers,
        "client": (client_ip, 12345),
        "app": None,
    }
    req = Request(scope)
    req.state.lang = "ru"
    req.state.user_hash = "mock_hash"
    req.state.is_lockdown = False
    return req


# =========================================================================
# 1. SECURITY TRAPS & RFC WELL-KNOWN WHITELIST
# =========================================================================

class TestSecurityTrapsAndWellKnown:
    """Verifies that RFC well-known paths and legitimate search crawlers never get penalized."""

    @pytest.mark.parametrize("path", [
        "/.well-known/apple-app-site-association",
        "/.well-known/apple-app-site-association/",
        "/.well-known/apple-app-site-association?target=app",
        "/.well-known/assetlinks.json",
        "/.well-known/security.txt",
        "/robots.txt",
        "/robots.txt?v=2",
        "/sitemap.xml",
    ])
    def test_whitelisted_paths_recognized(self, path):
        """Standard RFC service paths must be matched by is_whitelisted_well_known."""
        assert is_whitelisted_well_known(path) is True

    @pytest.mark.parametrize("path", [
        "/.well-known/apple-app-site-association",
        "/.well-known/assetlinks.json",
        "/.well-known/security.txt",
        "/robots.txt",
        "/sitemap.xml",
    ])
    def test_whitelisted_paths_never_trigger_should_trap_bot(self, path):
        """should_trap_bot must return False for all RFC service paths regardless of caller."""
        assert should_trap_bot(path, user_agent="Googlebot/2.1") is False
        assert should_trap_bot(path, user_agent="Applebot/0.1") is False
        assert should_trap_bot(path, user_agent="Mozilla/5.0") is False

    @pytest.mark.parametrize("crawler_ua", [
        "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
        "Mozilla/5.0 (compatible; Google-InspectionTool/1.0;)",
        "Mozilla/5.0 (compatible; YandexBot/3.0; +http://yandex.com/bots)",
        "Mozilla/5.0 (compatible; YandexMobileBot/3.0; +http://yandex.com/bots)",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15 (Applebot/0.1; +http://www.apple.com/go/applebot)",
        "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
        "DuckDuckBot/1.0; (+http://duckduckgo.com/duckduckbot.html)",
    ])
    def test_legitimate_crawlers_recognized(self, crawler_ua):
        """Legitimate search engine crawlers must be detected by is_legitimate_crawler."""
        assert is_legitimate_crawler(crawler_ua) is True

    def test_legitimate_crawler_not_flagged_by_headers(self):
        """Googlebot/Applebot without Accept-Language must NOT be classified as suspicious by is_bot_by_headers."""
        google_ua = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
        req = make_dummy_request(path="/b/", user_agent=google_ua)
        # Note: req has no accept-language header
        assert is_bot_by_headers(req) is False

    @pytest.mark.asyncio
    async def test_custom_404_handler_does_not_trap_apple_association_and_well_known(self):
        """Simulate real Googlebot incident (66.249.90.35 on /.well-known/apple-app-site-association).

        Must NOT add IP to IP_TROLL_CONFIG and must NOT register bot violation.
        """
        googlebot_ip = "66.249.90.35"
        googlebot_ua = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"

        # Clear state for clean test
        IP_TROLL_CONFIG.pop(googlebot_ip, None)
        BOT_VIOLATIONS.pop(googlebot_ip, None)

        req = make_dummy_request(
            path="/.well-known/apple-app-site-association",
            client_ip=googlebot_ip,
            user_agent=googlebot_ua,
        )

        with patch("site_tgach.main.honey_pot_troll", new_callable=AsyncMock) as mock_troll:
            resp = await custom_404_handler(req, HTTPException(status_code=404))

            # Must return 404 cleanly
            assert resp.status_code == 404
            # Honeypot troll must NOT be called
            mock_troll.assert_not_called()
            # IP must NOT be in troll config
            assert googlebot_ip not in IP_TROLL_CONFIG
            # No violation counted
            assert BOT_VIOLATIONS[googlebot_ip] == 0

    @pytest.mark.asyncio
    async def test_custom_404_handler_does_not_trap_crawler_on_deleted_thread(self):
        """Crawlers querying a 404 deleted thread (e.g. /b/res/999999.html) must not be trapped."""
        yandex_ip = "77.88.55.66"
        yandex_ua = "Mozilla/5.0 (compatible; YandexBot/3.0; +http://yandex.com/bots)"

        IP_TROLL_CONFIG.pop(yandex_ip, None)
        BOT_VIOLATIONS.pop(yandex_ip, None)

        req = make_dummy_request(
            path="/b/res/999999.html",
            client_ip=yandex_ip,
            user_agent=yandex_ua,
        )

        with patch("site_tgach.main.honey_pot_troll", new_callable=AsyncMock) as mock_troll:
            resp = await custom_404_handler(req, HTTPException(status_code=404))
            assert resp.status_code == 404
            mock_troll.assert_not_called()
            assert yandex_ip not in IP_TROLL_CONFIG
            assert BOT_VIOLATIONS[yandex_ip] == 0


# =========================================================================
# 2. MALICIOUS SCANNER TRAPS INTEGRITY
# =========================================================================

class TestMaliciousScannerTraps:
    """Verifies that malicious security vulnerability scanners are still trapped and penalized."""

    @pytest.mark.parametrize("malicious_path", [
        "/admin",
        "/admin/login",
        "/phpmyadmin",
        "/phpmyadmin/index.php",
        "/.git/config",
        "/.git/HEAD",
        "/.env",
        "/api/.env",
        "/setup.php",
        "/wp-login.php",
        "/wp-admin",
        "/autodiscover/autodiscover.xml",
        "/dump.sql",
        "/backup.zip",
        "/.aws/credentials",
        "/.ssh/id_rsa",
        "/+CSCOL+/",
        "/shell.php",
    ])
    def test_malicious_paths_detected_by_should_trap_bot(self, malicious_path):
        """Known scanner paths must return True from should_trap_bot."""
        assert should_trap_bot(malicious_path) is True

    @pytest.mark.parametrize("malicious_path", [
        "/.git/config",
        "/.env",
        "/phpmyadmin",
        "/admin",
    ])
    def test_malicious_paths_trapped_even_with_spoofed_googlebot_ua(self, malicious_path):
        """Attacker spoofing Googlebot UA to probe /.env or /.git must STILL be trapped."""
        spoofed_ua = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
        assert should_trap_bot(malicious_path, user_agent=spoofed_ua) is True

    @pytest.mark.asyncio
    async def test_custom_404_handler_traps_attacker_and_sets_troll_penalty(self):
        """Real vulnerability scan on /admin or /.env must trigger AUTO-TRAP and set 24h penalty."""
        attacker_ip = "198.51.100.44"
        IP_TROLL_CONFIG.pop(attacker_ip, None)
        BOT_VIOLATIONS.pop(attacker_ip, None)

        req = make_dummy_request(
            path="/phpmyadmin",
            client_ip=attacker_ip,
            user_agent="Masscan/1.0",
        )

        with patch("site_tgach.main.honey_pot_troll", new_callable=AsyncMock) as mock_troll:
            mock_troll.return_value = make_dummy_request() # dummy response

            await custom_404_handler(req, HTTPException(status_code=404))

            mock_troll.assert_called_once()
            assert attacker_ip in IP_TROLL_CONFIG
            assert IP_TROLL_CONFIG[attacker_ip]["mode"] == "slow"
            assert IP_TROLL_CONFIG[attacker_ip]["expires"] > time.time() + 80000
            assert BOT_VIOLATIONS[attacker_ip] >= 1


# =========================================================================
# 3. SSR HTML PAGES ACCESSIBILITY WITHOUT JAVASCRIPT
# =========================================================================

class MockState:
    lang = "ru"
    user_hash = "mock_hash_123"
    is_lockdown = False
    def t(self, *args, **kwargs):
        if len(args) > 1:
            return args[1]
        return args[0] if args else ""


class JinjaMockRequest:
    def __init__(self, path="/b/"):
        self.url = type("URL", (), {"path": path, "_url": f"https://tgach.top{path}"})()
        self.base_url = "https://tgach.top/"
        self.query_params = {}
        self.state = MockState()


@pytest.fixture
def jinja_env():
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    env.filters["pluralize"] = lambda count, one, few, many: many
    env.filters["format_post_text"] = lambda text: text
    env.filters["format_timestamp"] = lambda ts: "12:00:00"
    env.filters["format_poll"] = lambda poll: ""
    env.filters["format_iso_time"] = lambda ts: "2026-01-01T00:00:00Z"
    env.filters["bayan_label"] = lambda count, lang="ru": f"Баян x{count}"
    env.filters["clean_title"] = lambda text: text
    env.filters["nick_from_hash"] = lambda h: "Аноним"
    env.filters["user_hash"] = lambda uid: f"h_{uid}"
    env.filters["get_user_hash"] = lambda uid: f"h_{uid}"
    env.globals["static_version"] = "10.3"
    return env


class TestSSRNoJavaScriptAccessibility:
    """Verifies that boards and threads render completely in HTML for users without JS."""

    def test_board_ssr_renders_posts_and_noscript_notice(self, jinja_env):
        """board.jinja2 must render thread titles, posts, anon names and noscript styles."""
        template = jinja_env.get_template("board.jinja2")

        fake_posts = [
            {
                "id": 1001,
                "author_id": 999,
                "timestamp": 1700000000,
                "thread_type": "default",
                "is_pinned": False,
                "is_endless": False,
                "is_archived": False,
                "is_yours": False,
                "is_op": True,
                "report_count": 0,
                "content": {
                    "text": "Тестовый тред для проверки SSR без включенного JS!",
                    "sage": False,
                    "files": [
                        {
                            "type": "image",
                            "original_url": "/files/image1.jpg",
                            "thumbnail_url": "/files/thumb1.jpg",
                            "original_file_id": "img1",
                            "filename": "image1.jpg",
                        }
                    ],
                },
                "replies": [],
                "reply_count": 0,
            }
        ]

        context = {
            "request": JinjaMockRequest("/b/"),
            "board_id": "b",
            "boards": {"b": {"name": "Бред", "category": "popular"}},
            "board_info": {"name": "Бред", "description": "Случайные мысли"},
            "posts": fake_posts,
            "BOT_USERNAME": "testbot",
            "current_sort": "bump",
            "site_mode": "public",
            "session": {"user": None},
            "meta_image": "https://tgach.top/static/logo.png",
            "is_skeleton": False,
            "is_archived": False,
        }

        html = template.render(context)

        # 1. Post content, ID, and anon info must be present in HTML
        assert "Тестовый тред для проверки SSR без включенного JS!" in html
        assert "#1001" in html
        assert "/b/res/1001.html" in html
        assert "Аноним" in html

        # 2. <noscript> block must be present with explanation
        assert "<noscript>" in html
        assert "JavaScript отключен" in html
        assert "статическую версию" in html

        # 3. <noscript> CSS must hide loader and ensure thread-list and post containers are visible
        assert "#app-loader { display: none;" in html
        assert ".thread-list, .thread-container, .post { display: block !important; }" in html
        assert "noscript img" in html

        # 4. Containers must NOT have inline display: none
        assert '<div class="thread-list"' in html

    def test_thread_ssr_renders_op_and_replies_without_js(self, jinja_env):
        """thread.jinja2 must render OP post and all replies directly in HTML."""
        template = jinja_env.get_template("thread.jinja2")

        fake_op = {
            "id": 5001,
            "author_id": 111,
            "timestamp": 1700000000,
            "thread_type": "default",
            "is_pinned": False,
            "is_endless": False,
            "is_archived": False,
            "is_op_yours": False,
            "is_op_hidden": False,
            "report_count": 0,
            "content": {
                "text": "Главный OP пост обсуждения без JS!",
                "sage": False,
                "files": [
                    {
                        "type": "image",
                        "original_url": "/files/op_photo.jpg",
                        "thumbnail_url": "/files/op_thumb.jpg",
                        "original_file_id": "op_pic",
                        "filename": "op_photo.jpg",
                    }
                ],
            },
        }

        fake_replies = [
            {
                "id": 5002,
                "author_id": 222,
                "timestamp": 1700000060,
                "report_count": 0,
                "is_yours": False,
                "is_reply_to_you": False,
                "content": {
                    "text": "Первый ответ на тред, видимый анону через Lynx/Tor!",
                    "sage": False,
                    "files": [],
                },
            },
            {
                "id": 5003,
                "author_id": 333,
                "timestamp": 1700000120,
                "report_count": 0,
                "is_yours": False,
                "is_reply_to_you": False,
                "content": {
                    "text": "Второй ответ с подтверждением нативного SSR!",
                    "sage": False,
                    "files": [],
                },
            },
        ]

        context = {
            "request": JinjaMockRequest("/b/res/5001.html"),
            "board_id": "b",
            "boards": {"b": {"name": "Бред", "category": "popular"}},
            "board_info": {"name": "Бред", "description": "Случайные мысли"},
            "op_post": fake_op,
            "replies": fake_replies,
            "BOT_USERNAME": "testbot",
            "is_archived": False,
            "site_mode": "public",
            "session": {"user": None},
            "thread_type": "default",
            "is_unlocked": True,
            "meta_description": "Главный OP пост",
            "meta_image": "https://tgach.top/static/logo.png",
            "is_skeleton": False,
        }

        html = template.render(context)

        # 1. OP text and reply texts must be rendered
        assert "Главный OP пост обсуждения без JS!" in html
        assert "Первый ответ на тред, видимый анону через Lynx/Tor!" in html
        assert "Второй ответ с подтверждением нативного SSR!" in html
        assert "#5001" in html
        assert "#5002" in html
        assert "#5003" in html

        # 2. <noscript> notice must be present
        assert "<noscript>" in html
        assert "JavaScript отключен" in html

        # 3. Noscript styles must ensure .replies-list and .post are visible
        assert ".replies-list, .post, .op-post { display: block !important; }" in html

        # 4. Fallback media tags in noscript must exist for lazy images
        assert '<noscript><img src="/files/op_photo.jpg"' in html

    def test_catalog_ssr_renders_threads_grid(self, jinja_env):
        """catalog.jinja2 must render catalog-grid with threads and noscript notice."""
        template = jinja_env.get_template("catalog.jinja2")

        fake_threads = [
            {
                "id": 7001,
                "reply_count": 15,
                "content": {
                    "text": "Каталожный тред",
                    "files": [],
                },
            }
        ]

        context = {
            "request": JinjaMockRequest("/b/catalog/"),
            "board_id": "b",
            "boards": {"b": {"name": "Бред"}},
            "board_info": {"name": "Бред", "description": "Описание"},
            "threads": fake_threads,
            "site_mode": "public",
            "session": {"user": None},
            "is_skeleton": False,
            "current_sort": "bump",
        }

        html = template.render(context)

        assert "Каталожный тред" in html
        assert "/b/res/7001.html" in html
        assert 'id="catalog-grid"' in html
        # style must not have display: none when is_skeleton is False
        assert 'id="catalog-grid" style="display: none;"' not in html
        assert "<noscript>" in html
        assert ".catalog-grid { display: grid !important; }" in html
