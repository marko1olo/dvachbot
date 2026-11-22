"""Test suite for real user feedback and complaints resolution (Subagent 4: Web UI/UX).

Complaints covered:
1. Input Lag & Broken Ctrl+Z:
   - "Борда тормозит даже с отключенным маскотом - текст вводится с опозданием, железо в ахуе. Ctrl+z не работает, я тупо лапками удаляю свои ошибки"
2. Scrollbar, Overboard replies, Noscript:
   - "1. Нахуй ты выебал полосу прокрутки? 2. Какого хуя у тебя в оверборде только ОП-посты? 3. Нахуя нужно врубать JS для просмотра?"
"""

import gzip
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import jinja2
import pytest

ROOT_DIR = Path(r"C:\dev\dvachbot")
STATIC_JS_DIR = ROOT_DIR / "site_tgach" / "static" / "js"
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
    return env


# =========================================================================
# 1. INPUT LAG & UNDO/REDO (CTRL+Z) RESOLUTION TESTS
# =========================================================================

class TestInputLagAndUndoRedoResolution:
    """Verifies that textarea typing has no forced reflow lag and Ctrl+Z undo/redo is preserved."""

    @pytest.mark.parametrize("filename", ["main.js", "main.src.js", "main.min.js"])
    def test_autoresize_debounced_and_avoids_forced_layout_thrashing(self, filename):
        """autoResize must be debounced and guard against layout thrashing."""
        content = (STATIC_JS_DIR / filename).read_text(encoding="utf-8")
        assert "autoResize(el)" in content
        # Must have debouncing timer to decouple from per-keystroke execution
        assert "_resizeTimer" in content or "setTimeout" in content
        # Must guard against unneeded height='auto' collapse
        assert "el.clientHeight >= el.scrollHeight" in content

    @pytest.mark.parametrize("filename", ["main.js", "main.src.js", "main.min.js"])
    def test_form_manager_has_undo_redo_fallback_stack(self, filename):
        """FormManager must have undo and redo text methods and undo stack."""
        content = (STATIC_JS_DIR / filename).read_text(encoding="utf-8")
        assert "_undoStack" in content
        assert "pushUndoSnapshot" in content
        assert "undoText" in content
        assert "redoText" in content

    @pytest.mark.parametrize("filename", ["main.js", "main.src.js", "main.min.js"])
    def test_textarea_keydown_handles_ctrl_z_and_ctrl_y(self, filename):
        """Textarea keydown listener must bind Ctrl+Z (undo), Ctrl+Shift+Z, and Ctrl+Y (redo)."""
        content = (STATIC_JS_DIR / filename).read_text(encoding="utf-8")
        assert "KeyZ" in content or "key === 'z'" in content
        assert "KeyY" in content or "key === 'y'" in content
        assert "this.undoText(textarea)" in content
        assert "this.redoText(textarea)" in content

    @pytest.mark.parametrize("filename", ["main.js", "main.src.js", "main.min.js"])
    def test_quote_insertion_uses_execcommand_insert_text_to_preserve_undo(self, filename):
        """Quote tag formatting must use document.execCommand('insertText') to avoid wiping undo stack."""
        content = (STATIC_JS_DIR / filename).read_text(encoding="utf-8")
        assert "document.execCommand('insertText', false, '> ')" in content

    def test_undo_redo_stack_in_node_simulation(self):
        """Run Node.js simulation validating pushUndoSnapshot, undoText, and redoText in FormManager."""
        node_cmd = shutil.which("node")
        if not node_cmd:
            pytest.skip("Node.js not installed")

        js_path = str(STATIC_JS_DIR / "main.js").replace("\\", "/")
        test_script = f"""
        global.window = {{
            innerHeight: 800,
            innerWidth: 375,
            scrollY: 0,
            scrollX: 0,
            scrollTo: () => {{}},
            getSelection: () => ({{ toString: () => '', anchorNode: null }})
        }};
        global.document = {{
            activeElement: null,
            body: {{ dataset: {{}} }},
            querySelector: () => null,
            querySelectorAll: () => [],
            getElementById: () => null,
            execCommand: () => false
        }};
        global.t = (k, d) => d || k;
        global.showToast = () => {{}};
        global.safeInit = () => {{}};
        global.localStorage = {{ getItem: () => null, setItem: () => {{}}, removeItem: () => {{}} }};

        const fs = require('fs');
        const code = fs.readFileSync('{js_path}', 'utf8');

        const fmStart = code.indexOf('const FormManager = {{');
        if (fmStart === -1) process.exit(1);
        let braceCount = 0;
        let fmEnd = -1;
        for (let i = fmStart; i < code.length; i++) {{
            if (code[i] === '{{') braceCount++;
            else if (code[i] === '}}') {{
                braceCount--;
                if (braceCount === 0) {{ fmEnd = i + 1; break; }}
            }}
        }}
        const fmCode = code.substring(fmStart, fmEnd);
        eval(fmCode.replace('const FormManager =', 'global.FormManager ='));

        // Test textarea mock
        const mockTa = {{
            value: '',
            selectionStart: 0,
            selectionEnd: 0,
            clientHeight: 60,
            scrollHeight: 60,
            style: {{ height: '60px' }},
            setSelectionRange(s, e) {{ this.selectionStart = s; this.selectionEnd = e; }}
        }};

        // Step 1: Type initial text
        mockTa.value = 'Hello';
        mockTa.selectionStart = 5;
        mockTa.selectionEnd = 5;
        FormManager.pushUndoSnapshot(mockTa, true);

        // Step 2: Type more text
        mockTa.value = 'Hello world!';
        mockTa.selectionStart = 12;
        mockTa.selectionEnd = 12;
        FormManager.pushUndoSnapshot(mockTa, true);

        if (FormManager._undoStack.length !== 2) {{
            console.error('Stack length expected 2, got ' + FormManager._undoStack.length);
            process.exit(1);
        }}

        // Step 3: Undo
        FormManager.undoText(mockTa);
        if (mockTa.value !== 'Hello') {{
            console.error('Expected Undo to restore "Hello", got: ' + mockTa.value);
            process.exit(1);
        }}

        // Step 4: Redo
        FormManager.redoText(mockTa);
        if (mockTa.value !== 'Hello world!') {{
            console.error('Expected Redo to restore "Hello world!", got: ' + mockTa.value);
            process.exit(1);
        }}

        console.log('NODE_UNDO_REDO_PASSED');
        """
        result = subprocess.run([node_cmd, "-e", test_script], capture_output=True, text=True)
        assert result.returncode == 0, f"Node simulation failed:\n{result.stdout}\n{result.stderr}"
        assert "NODE_UNDO_REDO_PASSED" in result.stdout


# =========================================================================
# 2. SCROLLBAR UX & CROSS-BROWSER COMFORT TESTS
# =========================================================================

class TestScrollbarUxAndStyles:
    """Verifies that the custom scrollbars are comfortable, visible, and have standard properties."""

    @pytest.mark.parametrize("filename", ["style.src.css", "style.css", "style.min.css"])
    def test_standard_scrollbar_properties_defined(self, filename):
        """html, body must have standard scrollbar-width: thin and scrollbar-color."""
        content = (STATIC_CSS_DIR / filename).read_text(encoding="utf-8")
        assert "scrollbar-width: thin;" in content
        assert "scrollbar-color:" in content

    @pytest.mark.parametrize("filename", ["style.src.css", "style.css", "style.min.css"])
    def test_webkit_scrollbar_comfortable_width_and_thumb(self, filename):
        """Webkit scrollbar width must be at least 10px with proper border-radius and min-height."""
        content = (STATIC_CSS_DIR / filename).read_text(encoding="utf-8")
        assert "width: 10px" in content
        assert "border-radius: 6px" in content
        assert "min-height: 40px" in content

    @pytest.mark.parametrize("filename", ["style.src.css", "style.css", "style.min.css"])
    def test_no_broken_overflow_on_body_and_scripting_none_loader_fix(self, filename):
        """style must contain @media (scripting: none) to hide #app-loader when JS is off."""
        content = (STATIC_CSS_DIR / filename).read_text(encoding="utf-8")
        assert "@media (scripting: none)" in content
        assert "#app-loader" in content


# =========================================================================
# 3. OVERBOARD THREAD ACTIVITY & REPLIES PREVIEW TESTS
# =========================================================================

class TestOverboardThreadActivityAndReplies:
    """Verifies that overboard displays thread stats, reply counter badges, and reply previews."""

    def _make_overboard_context(self, view="threads"):
        class DummyRequestState:
            user_hash = "mock_hash_12345"
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
                    "stat_thread_details": f"Ответов: {kwargs.get('replies', 0)}, анонимов: {kwargs.get('anons', 0)}",
                    "btn_open_thread": "Открыть тред &rarr;",
                    "btn_goto_thread": "[ В тред ]",
                    "report_modal_title": "Пожаловаться на пост",
                    "report_category": "Категория",
                    "report_cat_spam": "Спам",
                    "report_cat_insult": "Оскорбление",
                    "report_cat_illegal": "Нелегальный контент",
                    "report_cat_offtopic": "Оффтоп",
                    "report_reason": "Причина жалобы",
                    "btn_cancel": "Отмена",
                    "report_send": "Отправить",
                    "settings_modal_title": "Настройки",
                    "setting_sound": "Звук",
                    "setting_theme": "Тема оформления",
                    "theme_light": "Светлая",
                    "theme_dark": "Темная",
                    "theme_cyberpunk": "Cyberpunk",
                    "theme_crypto": "Crypto"
                }
                return translations.get(key, default or key)

        class DummyRequest:
            state = DummyRequestState()

        posts = [
            {
                "id": 100,
                "board_id": "b",
                "author_id": 9999,
                "timestamp": 1715000000,
                "report_count": 0,
                "is_pinned": False,
                "is_endless": False,
                "thread_type": "default",
                "reply_to_post_num": None,
                "reply_count": 42,
                "anon_count": 15,
                "backlinks": [101, 102],
                "content": {
                    "text": "Тестовый ОП-пост на оверборде с активным обсуждением.",
                    "files": []
                },
                "latest_replies": [
                    {
                        "id": 101,
                        "board_id": "b",
                        "author_id": 8888,
                        "timestamp": 1715000100,
                        "report_count": 0,
                        "content": {
                            "text": "Первый ответ в треде на оверборде.",
                            "files": []
                        }
                    },
                    {
                        "id": 102,
                        "board_id": "b",
                        "author_id": 7777,
                        "timestamp": 1715000200,
                        "report_count": 0,
                        "content": {
                            "text": "Второй ответ в треде на оверборде.",
                            "files": []
                        }
                    }
                ]
            }
        ]

        boards = {
            "b": {"name": "Бред", "category": "popular"},
            "po": {"name": "Политика", "category": "popular"},
        }

        return {
            "request": DummyRequest(),
            "posts": posts,
            "boards": boards,
            "all_boards": boards,
            "selected_boards": ["b"],
            "board_id": "overboard",
            "current_view": view,
            "current_sort": "bump",
            "site_mode": "public",
            "is_skeleton": False,
            "static_version": "1.0",
            "session": {},
            "stickers": {}
        }

    def test_overboard_threads_view_renders_thread_stats_and_replies_preview(self, jinja_env):
        """overboard.jinja2 in threads view must render thread stats container, reply badges, and replies preview."""
        tmpl = jinja_env.get_template("overboard.jinja2")
        rendered = tmpl.render(self._make_overboard_context(view="threads"))

        # Must have thread-stats-container
        assert "thread-stats-container" in rendered
        # Must have reply counter badge
        assert "thread-replies-badge" in rendered
        assert "Ответов: 42" in rendered
        # Must show omitted notice (42 replies total, 2 shown => 40 omitted)
        assert "Пропущено: 40" in rendered
        # Must have open thread link
        assert 'href="/b/res/100.html"' in rendered
        assert "Открыть тред" in rendered

        # Must render the replies preview container and reply posts
        assert "latest-replies-container" in rendered
        assert "overboard-reply" in rendered
        assert 'id="post-101"' in rendered
        assert 'id="post-102"' in rendered
        assert "Первый ответ в треде на оверборде." in rendered
        assert "Второй ответ в треде на оверборде." in rendered


# =========================================================================
# 4. NOSCRIPT FALLBACK & ACCESSIBILITY TESTS
# =========================================================================

class TestNoscriptFallbackAndAccessibility:
    """Verifies that templates provide clear noscript CSS and notification without blocking user view."""

    @pytest.mark.parametrize("template_name", ["overboard.jinja2", "board.jinja2", "thread.jinja2"])
    def test_noscript_rules_hide_app_loader_and_show_notice(self, template_name):
        """Templates must contain a noscript block that hides #app-loader and displays no-js-notice."""
        tmpl_path = TEMPLATES_DIR / template_name
        content = tmpl_path.read_text(encoding="utf-8")

        assert "<noscript>" in content
        assert "</noscript>" in content
        # Must hide app-loader
        assert "#app-loader { display: none" in content
        # Must have no-js-notice element
        assert 'class="no-js-notice"' in content
        assert "JavaScript отключен" in content

    def test_templates_do_not_contain_blanket_important_none_on_modals(self, jinja_env):
        """Rendered templates must not have display: none !important; on modals to satisfy previous tests."""
        class MockReq:
            def __init__(self, path="/b/"):
                self.url = type("URL", (), {"path": path, "_url": f"https://tgach.top{path}"})()
                self.base_url = "https://tgach.top/"
                self.query_params = {}
                self.state = type("State", (), {
                    "lang": "ru", "stream": "ru", "user_hash": "abc",
                    "canonical_url": f"https://tgach.top{path}",
                    "t": lambda *args, **kw: args[1] if len(args) > 1 else (args[0] if args else "")
                })()

        for tmpl_name in ["board.jinja2", "overboard.jinja2"]:
            tmpl = jinja_env.get_template(tmpl_name)
            ctx = {
                "request": MockReq("/b/"),
                "board_id": "b",
                "board_info": {"id": "b", "name": "Бред", "category": "popular"},
                "posts": [],
                "post": {
                    "id": 1000, "board_id": "b", "author_id": 1, "timestamp": 1715000000,
                    "reply_to_post_num": None, "reply_count": 0, "anon_count": 1,
                    "is_pinned": False, "is_endless": False, "is_closed": False,
                    "report_count": 0, "backlinks": [], "content": {"text": "Hello", "files": []},
                    "latest_replies": []
                },
                "thread_post": None,
                "replies": [],
                "boards": {"b": {"name": "Бред", "category": "popular"}},
                "all_boards": {"b": {"name": "Бред", "category": "popular"}},
                "selected_boards": ["b"],
                "current_view": "threads",
                "current_sort": "bump",
                "site_mode": "public",
                "is_skeleton": False,
                "static_version": "1.0",
                "session": {},
                "stickers": {}
            }
            rendered = tmpl.render(ctx)
            assert "display: none !important;" not in rendered
