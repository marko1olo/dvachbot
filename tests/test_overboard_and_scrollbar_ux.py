# -*- coding: utf-8 -*-
"""
Tests for Red-Team Task 3: Overboard & Viewport UX Inquisitor.
Covers:
1. Ergonomic, accessible, and high-contrast scrollbars for both desktop and touch/mobile devices.
2. Dual-mode Overboard (?mode=catalog vs ?mode=live) with switcher [🧵 Каталог тредов] | [🔥 Живая лента ответов].
3. Live replies feed under threads on overboard with quotes, reply-links, and media previews.
4. Jinja2 context validity and form filter preservation.
"""

import gzip
import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import jinja2
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
STATIC_CSS_DIR = ROOT_DIR / "site_tgach" / "static" / "css"
TEMPLATES_DIR = ROOT_DIR / "site_tgach" / "templates"


@pytest.fixture(scope="module")
def jinja_env():
    """Jinja2 environment configured with filters used by site_tgach."""
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=jinja2.select_autoescape(["html", "jinja2"]),
    )

    env.filters["format_timestamp"] = lambda ts: "12.05.2024 14:30:00"
    env.filters["format_iso_time"] = lambda ts: "2024-05-12T14:30:00Z"
    env.filters["clean_title"] = lambda t: t or "Тред"
    env.filters["format_post_text"] = lambda text: text or ""
    env.filters["nick_from_hash"] = lambda h: f"Anon_{str(h)[:6]}"
    env.filters["striptags"] = lambda s: s or ""
    env.filters["truncate"] = lambda s, l=80: (s[:l] + "...") if s and len(s) > l else (s or "")
    env.filters["random"] = lambda lst: lst[0] if lst else ""
    env.filters["tojson"] = lambda obj: json.dumps(obj, ensure_ascii=False)
    env.filters["user_hash"] = lambda uid: f"h_{uid}"
    env.filters["get_user_hash"] = lambda uid: f"h_{uid}"
    env.filters["bayan_label"] = lambda c, lang="ru": f"Баян x{c}"

    return env


def make_dummy_request(query_params=None):
    """Creates a mock Request object for Jinja rendering and endpoint checks."""
    qp = query_params or {}

    class DummyRequestState:
        user_hash = "mock_hash_overboard"
        lang = "ru"
        stream = "ru"

        @staticmethod
        def t(key, default="", **kwargs):
            translations = {
                "site_name": "TGACH",
                "fav_title": "Избранное",
                "settings_btn_title": "Настройки",
                "theme_btn_title": "Тема",
                "logout_btn": "Выход",
                "nav_main": "Главная",
                "sort_label": "Сортировка:",
                "sort_bump": "По бампу",
                "sort_new": "По дате",
                "sort_random": "Случайно",
                "filter_boards": "Доски:",
                "filter_apply": "Применить",
                "anon_name": "Аноним",
                "you_marker": "(Вы)",
                "stat_replies": "Ответов",
                "stat_files": "Файлов",
                "stat_anons": "Анонов",
                "btn_open_thread": "Открыть тред &rarr;",
                "footer_text": "TGACH Overboard",
                "loading": "Загрузка...",
                "report_modal_title": "Пожаловаться на пост",
            }
            return translations.get(key, default or key)

    class DummyRequest:
        state = DummyRequestState()

    req = DummyRequest()
    req.query_params = qp
    return req


def make_overboard_sample_posts():
    """Generates sample OP posts with latest replies for template rendering."""
    return [
        {
            "id": 5001,
            "board_id": "b",
            "author_id": 11111,
            "timestamp": 1715000000,
            "report_count": 0,
            "is_pinned": False,
            "is_endless": False,
            "thread_type": "default",
            "reply_to_post_num": None,
            "reply_count": 10,
            "anon_count": 5,
            "files_count": 2,
            "backlinks": [5002, 5003],
            "content": {
                "text": "Главный тред дня: обсуждаем редизайн полосы прокрутки и ленту оверборда.",
                "files": [
                    {
                        "original_file_id": "op_pic_1.jpg",
                        "thumbnail_file_id": "op_pic_1_thumb.jpg",
                        "type": "photo",
                        "filename": "proof.jpg",
                    }
                ],
            },
            "latest_replies": [
                {
                    "id": 5002,
                    "board_id": "b",
                    "author_id": 22222,
                    "timestamp": 1715000120,
                    "report_count": 0,
                    "reply_to_post_num": 5001,
                    "content": {
                        "text": ">>5001 Наконец-то вернули живые ответы в оверборд!",
                        "files": [
                            {
                                "original_file_id": "reply_pic_1.png",
                                "thumbnail_file_id": "reply_pic_1_thumb.png",
                                "type": "image",
                                "filename": "kek.png",
                            }
                        ],
                    },
                },
                {
                    "id": 5003,
                    "board_id": "b",
                    "author_id": 33333,
                    "timestamp": 1715000240,
                    "report_count": 0,
                    "reply_to_post_num": 5002,
                    "content": {
                        "text": ">>5002 И полосу прокрутки сделали нормальной ширины, мышью попадать легко.",
                        "files": [],
                    },
                },
            ],
        }
    ]


# =========================================================================
# 1. SCROLLBAR ACCESSIBILITY & ERGONOMICS TESTS
# =========================================================================

class TestScrollbarAccessibilityAndErgonomics:
    """Verifies comfortable scrollbar width, contrast, touch media query, and absence of blocking rules."""

    @pytest.mark.parametrize("filename", ["style.src.css", "style.css", "style.min.css"])
    def test_scrollbar_width_is_ergonomic_at_least_10_to_12px(self, filename):
        """Scrollbar width must be at least 10-12px for comfortable desktop mouse grabbing."""
        content = (STATIC_CSS_DIR / filename).read_text(encoding="utf-8")
        assert "width: 12px" in content
        assert "min-width: 10px" in content
        assert "border-radius: 6px" in content
        assert "min-height: 40px" in content

    @pytest.mark.parametrize("filename", ["style.src.css", "style.css", "style.min.css"])
    def test_scrollbar_contrast_and_hover_effects(self, filename):
        """Scrollbar thumb must have contrast color and hover feedback."""
        content = (STATIC_CSS_DIR / filename).read_text(encoding="utf-8")
        assert "var(--border-input" in content
        assert "var(--accent-primary" in content
        assert "::-webkit-scrollbar-thumb:hover" in content

    @pytest.mark.parametrize("filename", ["style.src.css", "style.css", "style.min.css"])
    def test_scrollbar_standards_and_touch_devices(self, filename):
        """Standard scrollbar-width properties must be present and coarse pointer must respect native OS scrollbar."""
        content = (STATIC_CSS_DIR / filename).read_text(encoding="utf-8")
        assert "scrollbar-width: thin;" in content
        assert "scrollbar-color:" in content
        assert "@media (pointer: coarse)" in content
        assert "scrollbar-width: auto;" in content

    @pytest.mark.parametrize("filename", ["style.src.css", "style.css", "style.min.css"])
    def test_no_destructive_scrollbar_hiding_on_body(self, filename):
        """Main page body and html must NEVER hide scrollbars with width: 0 or display: none."""
        content = (STATIC_CSS_DIR / filename).read_text(encoding="utf-8")
        assert "body::-webkit-scrollbar { display: none" not in content
        assert "html::-webkit-scrollbar { display: none" not in content
        assert "body::-webkit-scrollbar { width: 0" not in content
        assert "html::-webkit-scrollbar { width: 0" not in content

    @pytest.mark.parametrize("filename", ["style.src.css", "style.css", "style.min.css"])
    def test_no_broken_unconditional_overflow_hidden_on_body(self, filename):
        """Body must not have unconditional overflow: hidden (only modal-open and gallery-open classes allowed)."""
        content = (STATIC_CSS_DIR / filename).read_text(encoding="utf-8")
        lines = content.splitlines()
        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if "overflow: hidden" in stripped or "overflow-y: hidden" in stripped:
                # Must be scoped to modal-open, gallery-open, or specific child containers
                assert any(
                    cls in stripped or cls in lines[max(0, idx - 3):idx]
                    for cls in [
                        "modal-open",
                        "gallery-open",
                        "upload-progress",
                        "toast",
                        "dropdown",
                        "preview",
                        "crop",
                        "badge",
                        "app-loader",
                    ]
                ) or "body {" not in stripped, f"Unscoped overflow: hidden found on line {idx}: {line}"


# =========================================================================
# 2. OVERBOARD ENDPOINT MODES & LOGIC TESTS
# =========================================================================

class TestOverboardEndpointModes:
    """Verifies that overboard_page supports ?mode=catalog and ?mode=live."""

    def test_overboard_code_supports_mode_catalog_and_mode_live(self):
        """site_tgach/main.py must parse mode parameter and set reply_limit accordingly."""
        main_py = ROOT_DIR / "site_tgach" / "main.py"
        code = main_py.read_text(encoding="utf-8")

        assert 'mode_param = request.query_params.get("mode"' in code
        assert 'overboard_mode = mode_param' in code
        assert 'reply_limit = 0 if overboard_mode == "catalog" else 3' in code
        assert '"current_mode": overboard_mode' in code
        assert 'cache_key = f"bot_overboard_html:{sort_mode}:{view_mode}:{overboard_mode}:' in code


# =========================================================================
# 3. OVERBOARD JINJA2 RENDERING & LIVE REPLIES TESTS
# =========================================================================

class TestOverboardJinja2RenderingAndModes:
    """Verifies that overboard.jinja2 correctly renders the mode switcher, catalog mode, and live feed mode."""

    def _make_context(self, mode="live", view="threads"):
        boards = {
            "b": {"name": "Бред", "category": "popular"},
            "po": {"name": "Политика", "category": "popular"},
        }
        return {
            "request": make_dummy_request(query_params={"mode": mode}),
            "posts": make_overboard_sample_posts(),
            "boards": boards,
            "all_boards": boards,
            "selected_boards": ["b"],
            "board_id": "overboard",
            "current_view": view,
            "current_mode": mode,
            "current_sort": "bump",
            "site_mode": "public",
            "is_skeleton": False,
            "static_version": "1.0",
            "session": {},
            "stickers": {},
        }

    def test_mode_switcher_rendered_in_header(self, jinja_env):
        """Header must contain mode switcher: [🧵 Каталог тредов] | [🔥 Живая лента ответов]."""
        tmpl = jinja_env.get_template("overboard.jinja2")
        rendered = tmpl.render(self._make_context(mode="live"))

        assert "overboard-mode-switcher" in rendered
        assert "[🧵 Каталог тредов]" in rendered
        assert "[🔥 Живая лента ответов]" in rendered
        assert "mode=catalog" in rendered
        assert "mode=live" in rendered

    def test_catalog_mode_shows_no_replies_and_activates_catalog_btn(self, jinja_env):
        """In mode=catalog, latest-replies-container must NOT be rendered, and catalog button is active."""
        tmpl = jinja_env.get_template("overboard.jinja2")
        rendered = tmpl.render(self._make_context(mode="catalog"))

        # Catalog button is active
        assert "btn-mode-toggle active" in rendered
        # Form has mode=catalog hidden input
        assert '<input type="hidden" name="mode" value="catalog">' in rendered

        # OP post is displayed
        assert "Главный тред дня" in rendered
        assert "thread-replies-badge" in rendered

        # Replies preview container is NOT rendered in catalog mode
        assert "latest-replies-container" not in rendered
        assert "overboard-reply" not in rendered
        assert "Наконец-то вернули живые ответы" not in rendered

    def test_live_mode_renders_replies_quotes_and_media(self, jinja_env):
        """In mode=live, latest replies container is rendered with quote links and image previews."""
        tmpl = jinja_env.get_template("overboard.jinja2")
        rendered = tmpl.render(self._make_context(mode="live"))

        # Live button is active
        assert "btn-mode-toggle active" in rendered
        # Form has mode=live hidden input
        assert '<input type="hidden" name="mode" value="live">' in rendered

        # OP post
        assert "Главный тред дня" in rendered

        # Live replies container must be present
        assert "latest-replies-container" in rendered
        assert "overboard-reply" in rendered
        assert 'id="post-5002"' in rendered
        assert 'id="post-5003"' in rendered

        # Quotes and reply texts
        assert "Наконец-то вернули живые ответы в оверборд!" in rendered
        assert "&gt;&gt;5001" in rendered or ">>5001" in rendered
        assert 'href="/b/res/5001.html#post-5001"' in rendered

        # Media preview in reply
        assert "reply_pic_1" in rendered
        assert "lazy-load" in rendered
        assert 'target="_blank"' in rendered
        assert "<noscript><img" in rendered

    def test_filter_form_preserves_current_mode(self, jinja_env):
        """Filters form must preserve mode on submission."""
        tmpl = jinja_env.get_template("overboard.jinja2")

        rendered_catalog = tmpl.render(self._make_context(mode="catalog"))
        assert '<input type="hidden" name="mode" value="catalog">' in rendered_catalog

        rendered_live = tmpl.render(self._make_context(mode="live"))
        assert '<input type="hidden" name="mode" value="live">' in rendered_live
