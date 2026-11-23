"""
Test suite for tgach.top frontend & templates fixes.
Verifies:
1. JavaScript syntax integrity & absence of broken constructs / accidental stopPropagation on quotes/stickers.
2. Jinja2 template rendering for chat.jinja2, board.jinja2, thread.jinja2, overboard.jinja2.
3. Absence of `display: none !important;` on #report-modal and valid modal CSS selectors.
4. Robustness of FormManager.smartReply, appendToTextarea, setReplyTo without null-pointer exceptions.
5. SystemDock mobile scroll controls logic (max height, touch listeners, safe visibility).
6. Synchronization of main.js, main.src.js, main.min.js and .gz bundles.
"""

import gzip
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
import pytest
from jinja2 import Environment, FileSystemLoader

REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC_JS_DIR = REPO_ROOT / "site_tgach" / "static" / "js"
TEMPLATES_DIR = REPO_ROOT / "site_tgach" / "templates"
STATIC_CSS_DIR = REPO_ROOT / "site_tgach" / "static" / "css"


# =========================================================================
# 1. JAVASCRIPT SYNTAX & CODE INTEGRITY
# =========================================================================

class TestJavaScriptSyntaxAndIntegrity:
    """Verifies that all JS assets pass node syntax checks and contain no regressed constructs."""

    @pytest.mark.parametrize("filename", ["main.js", "main.src.js", "main.min.js"])
    def test_node_syntax_validity(self, filename):
        """Node --check must validate all files without syntax errors."""
        file_path = STATIC_JS_DIR / filename
        assert file_path.exists(), f"{filename} does not exist"

        node_cmd = shutil.which("node")
        if not node_cmd:
            pytest.skip("node is not installed or not in PATH")

        result = subprocess.run(
            [node_cmd, "--check", str(file_path)],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Syntax error in {filename}:\n{result.stderr}"

    @pytest.mark.parametrize("filename", ["main.js", "main.src.js", "main.min.js"])
    def test_no_stop_propagation_on_quotes(self, filename):
        """Quote links must NOT have inline onclick='event.stopPropagation();'."""
        file_path = STATIC_JS_DIR / filename
        content = file_path.read_text(encoding="utf-8")

        # Check regex / pattern for quote link formatters
        bad_pattern = re.compile(r'class=["\']post-link["\'][^>]*onclick=["\'][^"\']*stopPropagation', re.IGNORECASE)
        match = bad_pattern.search(content)
        assert match is None, f"Found quote link with onclick stopPropagation in {filename}: {match.group(0)}"

    @pytest.mark.parametrize("filename", ["main.js", "main.src.js", "main.min.js"])
    def test_no_stop_propagation_on_sticker_images(self, filename):
        """Sticker images inside gallery-trigger must not trap clicks with onclick='event.stopPropagation();'."""
        file_path = STATIC_JS_DIR / filename
        content = file_path.read_text(encoding="utf-8")

        bad_pattern = re.compile(r'class=["\'][^"\']*post-sticker[^"\']*["\'][^>]*onclick=["\'][^"\']*stopPropagation', re.IGNORECASE)
        match = bad_pattern.search(content)
        assert match is None, f"Found sticker image with onclick stopPropagation in {filename}: {match.group(0)}"

    def test_post_preview_manager_allows_form_insertion_and_scroll(self):
        """PostPreviewManager click listener must insert into open forms and smooth scroll on second tap."""
        main_js = (STATIC_JS_DIR / "main.js").read_text(encoding="utf-8")

        # Verify it checks for active/open textareas
        assert "document.activeElement.tagName === 'TEXTAREA'" in main_js
        assert "FormManager.appendToTextarea(targetTa, postNum)" in main_js
        # Verify second tap scrolls to target post
        assert "link.classList.contains('preview-active')" in main_js
        assert "targetPost.scrollIntoView({ behavior: 'smooth', block: 'center' })" in main_js
        # Verify reply button is present in preview actions
        assert "btn-reply-post" in main_js
        assert "FormManager.smartReply(num, e)" in main_js

    def test_document_click_listener_supports_chat_and_board_reply(self):
        """Document click listener for .post-num-link must not be restricted strictly to /res/ pages."""
        main_js = (STATIC_JS_DIR / "main.js").read_text(encoding="utf-8")
        assert "location.pathname.includes('/res/') || location.pathname.includes('/chat/')" in main_js


# =========================================================================
# 2. JINJA2 TEMPLATES RENDERING & STICKER/QUOTE VERIFICATION
# =========================================================================

class MockState:
    lang = "ru"
    def t(self, *args, **kwargs):
        if len(args) > 1:
            return args[1]
        return args[0] if args else ""

class MockRequest:
    def __init__(self, path="/b/chat/"):
        self.url = type("URL", (), {"path": path, "_url": f"https://tgach.top{path}"})()
        self.base_url = "https://tgach.top/"
        self.query_params = {}
        self.state = MockState()


@pytest.fixture
def jinja_env():
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    # Register filters matching site_tgach/main.py
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


class TestJinja2TemplatesRendering:
    """Verifies that templates render correctly and comply with frontend requirements."""

    def _make_context(self, path="/b/"):
        return {
            "request": MockRequest(path),
            "session": {"user": {"id": 100, "username": "Anon", "is_guest": False, "role": "admin"}},
            "board_id": "b",
            "boards": {"b": {"name": "Бред", "username": "tgach_b"}},
            "all_boards": {"b": {"name": "Бред", "username": "tgach_b"}},
            "board_info": {"id": "b", "name": "Бред", "username": "tgach_b"},
            "posts": [
                {
                    "id": 1001,
                    "thread_id": None,
                    "author_id": 100,
                    "reply_count": 1,
                    "latest_replies": [],
                    "timestamp": 1700000000,
                    "content": {
                        "type": "text",
                        "text": ">>1000 Тестовый пост с цитатой",
                        "sage": False,
                        "is_censored": False,
                        "files": [
                            {
                                "type": "sticker",
                                "original_file_id": "file_stk_1",
                                "thumbnail_file_id": "file_stk_1_th",
                                "filename": "sticker.webp",
                                "blurhash": None
                            }
                        ]
                    }
                }
            ],
            "op_post": {
                "id": 1000,
                "thread_id": None,
                "author_id": 200,
                "timestamp": 1699999000,
                "content": {
                    "type": "text",
                    "text": "OP тред с стикером",
                    "sage": False,
                    "is_censored": False,
                    "files": [
                        {
                            "type": "sticker",
                            "original_file_id": "file_stk_op",
                            "thumbnail_file_id": "file_stk_op_th",
                            "filename": "animated.webm",
                            "blurhash": None
                        }
                    ]
                }
            },
            "thread_id": 1000,
            "replies": [],
            "total_pages": 1,
            "current_page": 1,
            "threads": [],
            "recent_threads": [],
            "stats": {},
        }

    def test_chat_template_rendering(self, jinja_env):
        """chat.jinja2 must render cleanly with no !important on modals and data-post-num on post numbers."""
        tmpl = jinja_env.get_template("chat.jinja2")
        rendered = tmpl.render(self._make_context("/b/chat/"))

        # Verify modals have no display: none !important;
        assert '<div class="modal" id="report-modal" style="display: none;">' in rendered
        assert '<div class="modal-overlay" id="modal-overlay" style="display: none;">' in rendered
        assert '<div class="modal" id="quick-reply-modal" style="display: none;">' in rendered
        assert "display: none !important;" not in rendered

        # Verify post number links have data-post-num
        assert 'class="post-num-link" data-post-num="1001"' in rendered

        # Verify sticker wrapper is rendered
        assert 'class="sticker-wrapper"' in rendered
        assert 'class="post-sticker lazy-load"' in rendered

    def test_board_template_rendering(self, jinja_env):
        """board.jinja2 must render stickers with class post-sticker (not generic post-image)."""
        tmpl = jinja_env.get_template("board.jinja2")
        rendered = tmpl.render(self._make_context("/b/"))

        assert '<div class="modal" id="report-modal" style="display: none;">' in rendered
        assert "display: none !important;" not in rendered
        assert 'class="sticker-wrapper"' in rendered
        assert 'class="post-sticker lazy-load' in rendered

    def test_thread_template_rendering(self, jinja_env):
        """thread.jinja2 must render OP animated webm sticker and reply stickers correctly."""
        tmpl = jinja_env.get_template("thread.jinja2")
        rendered = tmpl.render(self._make_context("/b/res/1000.html"))

        assert '<div class="modal" id="report-modal" style="display: none;">' in rendered
        assert "display: none !important;" not in rendered
        assert 'class="sticker-wrapper"' in rendered
        # WebM sticker renders as video.post-sticker
        assert '<video class="post-sticker' in rendered

    def test_overboard_template_rendering(self, jinja_env):
        """overboard.jinja2 must render sticker wrappers."""
        tmpl = jinja_env.get_template("overboard.jinja2")
        rendered = tmpl.render(self._make_context("/overboard/"))

        assert 'class="sticker-wrapper"' in rendered
        assert 'class="post-sticker lazy-load"' in rendered


# =========================================================================
# 3. REPORT MODAL CSS SELECTORS & DISPLAY PROPERTIES
# =========================================================================

class TestReportModalCssAndBehavior:
    """Verifies that #report-modal has no CSS conflicts preventing display."""

    def test_no_important_none_in_any_template(self):
        """Scan all Jinja2 templates in site_tgach for 'report-modal.*!important'."""
        for tmpl_path in TEMPLATES_DIR.glob("*.jinja2"):
            content = tmpl_path.read_text(encoding="utf-8")
            assert not re.search(r'id=["\']report-modal["\'][^>]*style=["\'][^"\']*display:\s*none\s*!important', content, re.IGNORECASE), \
                f"Found display: none !important on #report-modal in {tmpl_path.name}"
            assert not re.search(r'style=["\'][^"\']*display:\s*none\s*!important[^"\']*["\'][^>]*id=["\']report-modal["\']', content, re.IGNORECASE), \
                f"Found display: none !important on #report-modal in {tmpl_path.name}"

    def test_open_modal_resets_inline_display_property(self):
        """openModal in main.js must remove 'display' before setting display = 'block'."""
        main_js = (STATIC_JS_DIR / "main.js").read_text(encoding="utf-8")
        assert "modal.style.removeProperty('display')" in main_js
        assert "modal.style.display = 'block'" in main_js
        assert "overlay.style.removeProperty('display')" in main_js


# =========================================================================
# 4. FORMMANAGER & SMARTREPLY LOGIC INTEGRITY
# =========================================================================

class TestFormManagerAndSmartReply:
    """Verifies FormManager.smartReply null-safety and execution in simulated headless node."""

    def test_smart_reply_source_structure(self):
        """smartReply must handle missing .form-container and guard all dom operations."""
        main_js = (STATIC_JS_DIR / "main.js").read_text(encoding="utf-8")

        # getContainer searches multiple variants including chat container
        assert "f.closest('.form-container')" in main_js
        assert "f.closest('.chat-form-container')" in main_js
        # nearbyForm checks boundingClientRect safely
        assert "typeof targetEl.getBoundingClientRect !== 'function'" in main_js
        # form fallback
        assert "document.querySelector('#post-form')" in main_js
        # textarea guard
        assert "this.appendToTextarea(textarea, postNum)" in main_js
        # appendToTextarea null guard
        assert "if (!el) return;" in main_js
        # setReplyTo null guard
        assert "(this.forms || []).forEach" in main_js

    def test_smart_reply_in_node_simulation(self):
        """Simulate FormManager.smartReply execution in Node.js with mock DOM without throwing."""
        node_cmd = shutil.which("node")
        if not node_cmd:
            pytest.skip("node is not installed or not in PATH")

        # Create a small script testing FormManager.smartReply in headless mock DOM
        test_script = r"""
        global.window = { innerHeight: 800, innerWidth: 375, getSelection: () => ({ toString: () => '', anchorNode: null }) };
        global.document = {
            activeElement: null,
            body: { dataset: {} },
            querySelector: (sel) => null,
            querySelectorAll: (sel) => [],
            getElementById: (id) => null
        };
        global.t = (k, d) => d || k;
        global.showToast = (msg) => {};
        global.safeInit = () => {};
        global.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };

        // Extract FormManager definition from main.js
        const fs = require('fs');
        const code = fs.readFileSync('""" + str(STATIC_JS_DIR / "main.js").replace("\\", "/") + r"""', 'utf8');
        
        // Isolate FormManager block using brace matching
        const fmStart = code.indexOf('const FormManager = {');
        if (fmStart === -1) {
            console.error("FormManager block not found");
            process.exit(1);
        }
        let braceCount = 0;
        let fmEnd = -1;
        for (let i = fmStart; i < code.length; i++) {
            if (code[i] === '{') braceCount++;
            else if (code[i] === '}') {
                braceCount--;
                if (braceCount === 0) {
                    fmEnd = i + 1;
                    break;
                }
            }
        }
        const fmCode = code.substring(fmStart, fmEnd).replace('const FormManager =', 'global.FormManager =') + ';';
        eval(fmCode);

        // Test 1: smartReply with null forms and no .form-container (should not throw)
        try {
            FormManager.forms = [];
            FormManager.mainForm = null;
            FormManager.floatingBox = null;
            FormManager.smartReply(12345, null);
            console.log("TEST1_PASSED");
        } catch (e) {
            console.error("TEST1_FAILED", e);
            process.exit(1);
        }

        // Test 2: appendToTextarea with null element (should gracefully return)
        try {
            FormManager.appendToTextarea(null, 12345);
            console.log("TEST2_PASSED");
        } catch (e) {
            console.error("TEST2_FAILED", e);
            process.exit(1);
        }

        // Test 3: smartReply with mock textarea and form without container
        try {
            let insertedValue = "";
            const mockTa = {
                value: "",
                selectionStart: 0,
                selectionEnd: 0,
                focus: () => {},
                setRangeText: (txt) => { insertedValue += txt; },
                dispatchEvent: () => {},
                style: {}
            };
            const mockForm = {
                querySelector: (sel) => sel === 'textarea' ? mockTa : null,
                classList: { contains: () => false, remove: () => {}, add: () => {} },
                getBoundingClientRect: () => ({ top: 100, bottom: 200 }),
                offsetHeight: 100,
                getClientRects: () => [{}],
                scrollIntoView: () => {},
                closest: (sel) => null
            };
            FormManager.forms = [mockForm];
            FormManager.smartReply(55555, null);
            if (insertedValue.includes(">>55555")) {
                console.log("TEST3_PASSED");
            } else {
                console.error("TEST3_FAILED: quote not inserted, value: " + insertedValue);
                process.exit(1);
            }
        } catch (e) {
            console.error("TEST3_FAILED", e);
            process.exit(1);
        }
        """

        result = subprocess.run([node_cmd, "-e", test_script], capture_output=True, text=True)
        assert result.returncode == 0, f"Node simulation failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        assert "TEST1_PASSED" in result.stdout
        assert "TEST2_PASSED" in result.stdout
        assert "TEST3_PASSED" in result.stdout


# =========================================================================
# 5. SYSTEMDOCK MOBILE SCROLL CONTROLS
# =========================================================================

class TestSystemDockScrollControls:
    """Verifies that SystemDock scroll controls use proper document height calculation and touch handlers."""

    def test_scroll_down_uses_document_element_scroll_height(self):
        """Scroll down must take Math.max of document.body and document.documentElement."""
        main_js = (STATIC_JS_DIR / "main.js").read_text(encoding="utf-8")
        assert "document.documentElement ? document.documentElement.scrollHeight : 0" in main_js
        assert "window.scrollTo({ top: max, behavior: \"smooth\" })" in main_js

    def test_scroll_buttons_bind_touchend(self):
        """Scroll buttons must bind touchend for instantaneous response on mobile devices."""
        main_js = (STATIC_JS_DIR / "main.js").read_text(encoding="utf-8")
        assert "btnUp.addEventListener('touchend', doScrollUp" in main_js
        assert "btnDown.addEventListener('touchend', doScrollDown" in main_js


# =========================================================================
# 6. ASSET SYNCHRONIZATION & GZIP BUNDLES
# =========================================================================

class TestAssetSynchronizationAndGzip:
    """Verifies that main.js, main.src.js, main.min.js and .gz files are synced and valid."""

    def test_main_src_js_synced_with_main_js(self):
        """main.src.js must match main.js."""
        main_js = (STATIC_JS_DIR / "main.js").read_text(encoding="utf-8")
        main_src = (STATIC_JS_DIR / "main.src.js").read_text(encoding="utf-8")
        assert main_js == main_src, "main.src.js is not synchronized with main.js"

    def test_main_js_gz_valid_and_matches_main_js(self):
        """main.js.gz must decompress to the exact bytes of main.js."""
        raw_js = (STATIC_JS_DIR / "main.js").read_bytes()
        gz_path = STATIC_JS_DIR / "main.js.gz"
        assert gz_path.exists(), "main.js.gz is missing"
        decompressed = gzip.decompress(gz_path.read_bytes())
        assert decompressed == raw_js, "main.js.gz does not match main.js"

    def test_main_min_js_gz_valid_and_matches_main_min_js(self):
        """main.min.js.gz must decompress to the exact bytes of main.min.js."""
        raw_min = (STATIC_JS_DIR / "main.min.js").read_bytes()
        gz_path = STATIC_JS_DIR / "main.min.js.gz"
        assert gz_path.exists(), "main.min.js.gz is missing"
        decompressed = gzip.decompress(gz_path.read_bytes())
        assert decompressed == raw_min, "main.min.js.gz does not match main.min.js"

    def test_main_min_js_contains_no_stopPropagation_on_quote_onclick(self):
        """Decompressed minified code must not have onclick='event.stopPropagation();' on quotes."""
        gz_path = STATIC_JS_DIR / "main.min.js.gz"
        decompressed = gzip.decompress(gz_path.read_bytes()).decode("utf-8", errors="replace")
        assert 'onclick="event.stopPropagation();"' not in decompressed
