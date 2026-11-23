"""
Test suite for tgach.top Web UI/UX, Mobile Responsiveness, and Inquisitor Audits.

Verifies:
1. Mobile responsiveness: overflow-x prevention, touch target size >= 36px for buttons,
   board tabs, pagination links, and tags.
2. Proof of Work (PoW) modal: loading animation, progress indicator, error handling,
   and retry button.
3. Error pages (404 / 500): elimination of dead-end screens with return buttons
   ("Вернуться на доску", "В каталог", "На главную").
4. Gallery & Media player: ESC key modal close, backdrop tap close, and inline video
   attributes (playsinline, webkit-playsinline, elimination of black screen #000 background).
5. Empty states: styled, user-friendly empty state block for search and tags.
6. Asset synchronization between source and minified/served files.
"""

import gzip
import os
import re
import shutil
import subprocess
from pathlib import Path
import pytest
from jinja2 import Environment, FileSystemLoader

REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC_JS_DIR = REPO_ROOT / "site_tgach" / "static" / "js"
TEMPLATES_DIR = REPO_ROOT / "site_tgach" / "templates"
STATIC_CSS_DIR = REPO_ROOT / "site_tgach" / "static" / "css"


class MockState:
    lang = "ru"

    def t(self, *args, **kwargs):
        if len(args) > 1 and args[1] is not None:
            return args[1]
        fallbacks = {
            "error_404_desc": "Похоже, этот тред утонул или был удален.",
            "error_404_fun": "Впрочем, в мультивселенной возможно всё.",
            "error_500_desc": "Админ уже выехал чинить.",
            "error_500_fun": "Админ уже выехал с паяльником.",
            "error_return": "На главную",
            "error_catalog": "В каталог",
            "error_back_board": "Вернуться на доску",
            "search_empty_title": "Ничего не найдено",
            "search_empty_desc": "По запросу ничего не нашлось. Попробуйте изменить запрос.",
            "nav_tags": "Облако тегов",
            "nav_overboard": "Все треды (/all/)",
            "nav_home": "На главную",
            "search_placeholder": "Поиск...",
            "no_tags_title": "Теги пока не найдены",
            "no_tags_found": "Теги еще не извлечены. Нужно больше постов!",
        }
        key = args[0] if args else ""
        return fallbacks.get(key, key)


class MockRequest:
    def __init__(self, path="/"):
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


# =========================================================================
# 1. ERROR PAGES (404 / 500)
# =========================================================================

class TestErrorPagesUx:
    """Verifies that error.jinja2 provides return navigation buttons and no dead ends."""

    def test_error_404_rendering(self, jinja_env):
        tmpl = jinja_env.get_template("error.jinja2")
        html = tmpl.render(
            request=MockRequest("/unknown/page"),
            status_code=404,
            detail="Страница не найдена",
            board_id="b",
        )
        assert "404" in html
        assert "Страница не найдена" in html
        # Check return buttons
        assert "error-actions" in html
        assert "Вернуться на доску" in html or "history.back" in html
        assert "В каталог" in html or "/catalog/" in html
        assert "На главную" in html or 'href="/"' in html

    def test_error_500_rendering(self, jinja_env):
        tmpl = jinja_env.get_template("error.jinja2")
        html = tmpl.render(
            request=MockRequest("/b/res/123"),
            status_code=500,
            detail="Внутренняя ошибка сервера",
            board_id="b",
        )
        assert "500" in html
        assert "Внутренняя ошибка сервера" in html
        assert "error-actions" in html
        assert 'href="/b/catalog/"' in html or 'href="/' in html
        assert 'href="/"' in html


# =========================================================================
# 2. EMPTY STATES (SEARCH & TAGS)
# =========================================================================

class TestEmptyStatesUx:
    """Verifies that empty searches and empty tags render a modern .empty-state block."""

    def test_search_results_empty_state_text(self, jinja_env):
        tmpl = jinja_env.get_template("search_results.jinja2")
        html = tmpl.render(
            request=MockRequest("/search?query=nonexistent12345"),
            query="nonexistent12345",
            posts=[],
            search_images=[],
            is_tag_search=False,
            boards={"b": {"name": "Бред", "description": "Бред"}},
            session={"user": None},
        )
        assert "empty-state" in html
        assert "empty-state-icon" in html
        assert "empty-state-title" in html
        assert "Ничего не найдено" in html
        assert "empty-state-actions" in html
        assert 'href="/tags/"' in html
        assert 'href="/overboard/"' in html
        assert 'href="/"' in html

    def test_search_results_empty_state_tag(self, jinja_env):
        tmpl = jinja_env.get_template("search_results.jinja2")
        html = tmpl.render(
            request=MockRequest("/tags/anime"),
            query="anime",
            current_tag="anime",
            posts=[],
            search_images=[],
            is_tag_search=True,
            boards={"b": {"name": "Бред", "description": "Бред"}},
            session={"user": None},
        )
        assert "empty-state" in html
        assert "Ничего не найдено" in html

    def test_tags_index_empty_state(self, jinja_env):
        tmpl = jinja_env.get_template("tags_index.jinja2")
        html = tmpl.render(
            request=MockRequest("/tags/"),
            tags=[],
            meta_title="Теги",
            meta_description="Все теги борды",
        )
        assert "empty-state" in html
        assert "Теги пока не найдены" in html or "Теги еще не извлечены" in html

    def test_tags_index_with_tags_touch_targets(self, jinja_env):
        tmpl = jinja_env.get_template("tags_index.jinja2")
        html = tmpl.render(
            request=MockRequest("/tags/"),
            tags=[("anime", 150), ("memes", 320), ("it", 80)],
            meta_title="Теги",
            meta_description="Все теги",
        )
        assert "tag-item" in html
        assert "#anime" in html
        assert "min-height: 36px" in html or "min-height" in (STATIC_CSS_DIR / "style.src.css").read_text(encoding="utf-8")


# =========================================================================
# 3. PROOF OF WORK (PoW) MODAL & VERIFICATION
# =========================================================================

class TestProofOfWorkUx:
    """Verifies that PoW has an interactive modal with progress indicator, animation, and retry."""

    def test_pow_js_implementation(self):
        js = (STATIC_JS_DIR / "main.js").read_text(encoding="utf-8")
        assert "const PoW = {" in js
        assert "createOrGetModal()" in js
        assert "pow-modal" in js
        assert "pow-progress-wrapper" in js
        assert "pow-retry-btn" in js
        assert "pow-cancel-btn" in js
        assert "showModal()" in js
        assert "showError(" in js
        assert "showSuccess()" in js
        assert "solveWithWorker" in js
        assert "updateProgress" in js

    def test_pow_css_styles(self):
        css = (STATIC_CSS_DIR / "style.src.css").read_text(encoding="utf-8")
        assert "#pow-modal" in css
        assert ".pow-modal-card" in css
        assert ".pow-progress-bar" in css
        assert "@keyframes powIndeterminate" in css
        assert "@keyframes shieldPulse" in css
        assert ".pow-actions" in css


# =========================================================================
# 4. GALLERY & MEDIA PLAYER UX
# =========================================================================

class TestGalleryAndMediaPlayerUx:
    """Verifies ESC key modal close, backdrop tap close, and inline iOS video attributes."""

    def test_gallery_escape_key_listener(self):
        js = (STATIC_JS_DIR / "main.js").read_text(encoding="utf-8")
        # Ensure GalleryManager handles Escape key
        assert "if (e.key === 'Escape') {" in js
        assert "this.close();" in js

    def test_gallery_backdrop_tap_listener(self):
        js = (STATIC_JS_DIR / "main.js").read_text(encoding="utf-8")
        # Ensure backdrop click or touch handles closing
        assert "this.handleBackgroundClick()" in js

    def test_video_popup_manager_touch_and_esc(self):
        js = (STATIC_JS_DIR / "main.js").read_text(encoding="utf-8")
        assert "const VideoPopupManager = {" in js
        assert "_handleEsc" in js
        assert "_boundTouch" in js or "touchend" in js

    def test_video_ios_safari_attributes(self):
        """Video elements in templates must contain playsinline, webkit-playsinline and no black background."""
        for tmpl_name in ["board.jinja2", "thread.jinja2", "search_results.jinja2", "overboard.jinja2"]:
            tmpl_path = TEMPLATES_DIR / tmpl_name
            content = tmpl_path.read_text(encoding="utf-8")
            # Verify no background: #000 on video tags
            for line in content.splitlines():
                if "<video" in line or ("background: #000;" in line and "video" in line.lower()):
                    assert "background: #000;" not in line, f"Found black video background in {tmpl_name}: {line}"
            # Check playsinline attributes
            assert "playsinline" in content
            assert "webkit-playsinline" in content

    def test_smartloader_video_loaded_hooks(self):
        """SmartLoader must set playsInline, muted, and handle onloadedmetadata/oncanplay without black screen."""
        js = (STATIC_JS_DIR / "main.js").read_text(encoding="utf-8")
        assert "img.playsInline = true;" in js
        assert "img.setAttribute('webkit-playsinline', '');" in js
        assert "onVideoLoaded" in js
        assert "img.onloadedmetadata = onVideoLoaded;" in js
        assert "img.oncanplay = onVideoLoaded;" in js


# =========================================================================
# 5. MOBILE RESPONSIVENESS (<768px / <480px) & TOUCH TARGETS
# =========================================================================

class TestMobileResponsivenessAndTouchTargets:
    """Verifies overflow-x prevention, touch target size >= 36px, and mobile layout rules."""

    def test_overflow_x_prevention(self):
        css = (STATIC_CSS_DIR / "style.src.css").read_text(encoding="utf-8")
        assert "html, body {" in css
        assert "overflow-x: hidden !important;" in css

    def test_touch_targets_minimum_size(self):
        css = (STATIC_CSS_DIR / "style.src.css").read_text(encoding="utf-8")
        # Verify min-height 36px is applied to mobile interactive elements
        assert "min-height: 36px" in css
        assert "min-width: 36px" in css
        assert ".board-nav a" in css
        assert ".page-link" in css
        assert ".tag-item" in css

    def test_catalog_grid_small_mobile_two_columns(self):
        css = (STATIC_CSS_DIR / "style.src.css").read_text(encoding="utf-8")
        assert "@media (max-width: 480px)" in css
        assert "grid-template-columns: repeat(2, 1fr)" in css

    def test_empty_state_css_exists(self):
        css = (STATIC_CSS_DIR / "style.src.css").read_text(encoding="utf-8")
        assert ".empty-state {" in css
        assert ".empty-state-icon {" in css
        assert ".empty-state-title {" in css
        assert ".empty-state-actions {" in css


# =========================================================================
# 6. ASSET SYNCHRONIZATION AND SYNTAX INTEGRITY
# =========================================================================

class TestAssetIntegrity:
    """Verifies that JS has valid syntax and that minified/source assets are properly in sync."""

    def test_node_syntax_validity_if_node_available(self):
        node_cmd = shutil.which("node")
        if not node_cmd:
            pytest.skip("node is not installed or not in PATH")

        for filename in ["main.js", "main.min.js", "main.src.js"]:
            file_path = STATIC_JS_DIR / filename
            result = subprocess.run(
                [node_cmd, "--check", str(file_path)],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, f"Syntax error in {filename}:\n{result.stderr}"

    def test_js_assets_in_sync(self):
        main_js = (STATIC_JS_DIR / "main.js").read_text(encoding="utf-8")
        min_js = (STATIC_JS_DIR / "main.min.js").read_text(encoding="utf-8")
        assert main_js == min_js, "main.js and main.min.js must be identical"

    def test_css_assets_contain_critical_rules(self):
        for filename in ["style.src.css", "style.min.css", "style.css"]:
            content = (STATIC_CSS_DIR / filename).read_text(encoding="utf-8")
            assert "#pow-modal" in content, f"{filename} missing #pow-modal"
            assert ".empty-state" in content, f"{filename} missing .empty-state"
            assert "min-height: 36px" in content, f"{filename} missing touch-target min-height"
