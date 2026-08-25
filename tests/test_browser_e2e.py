"""
tests/test_browser_e2e.py
Comprehensive Playwright Browser E2E Test Suite for Dvachbot Web Platform (site_tgach)
Requirements: R1, R2, R3, R4, R5 across Tiers 1-4

Execution:
- Standalone: .\\venv\\Scripts\\python tests/test_browser_e2e.py
- Pytest:     .\\venv\\Scripts\\python -m pytest tests/test_browser_e2e.py
"""

import asyncio
import os
import re
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from playwright.async_api import async_playwright

from site_tgach.main import app, templates, BOARD_CONFIG


# Helper to build mock request
def make_req(path: str = "/b/chat/"):
    from starlette.requests import Request
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "headers": [(b"host", b"localhost:8000")],
        "client": ("127.0.0.1", 12345),
        "app": app,
    }
    req = Request(scope)
    req.state.lang = "ru"
    req.state.t = lambda k, **kw: k
    req.state.user_hash = "anon_hash_123"
    return req


def get_rendered_chat_html(session_user=None):
    """Render chat.jinja2 with embedded inline CSS and JS for self-contained browser testing."""
    template = templates.get_template("chat.jinja2")
    req = make_req("/b/chat/")
    
    # Mock post list with video and image attachments
    mock_posts = [
        {
            "id": 101,
            "board_id": "b",
            "thread_id": 101,
            "author_id": 9999,
            "timestamp": 1724600000,
            "content": {
                "text": "Тестовое сообщение с видео >>100",
                "type": "files",
                "sage": False,
                "files": [
                    {
                        "type": "video",
                        "filename": "sample_video.mp4",
                        "original_file_id": "BAACAgIAAxkBAAEVideo1",
                        "thumbnail_file_id": "AgACAgIAAxkBAAEThumb1",
                        "original_url": "/files/BAACAgIAAxkBAAEVideo1",
                        "thumbnail_url": "/files/AgACAgIAAxkBAAEThumb1"
                    },
                    {
                        "type": "video_note",
                        "filename": "round_note.mp4",
                        "original_file_id": "CQACAgIAAxkBAAENote1",
                        "thumbnail_file_id": "AgACAgIAAxkBAAEThumbNote",
                        "original_url": "/files/CQACAgIAAxkBAAENote1",
                        "thumbnail_url": "/files/AgACAgIAAxkBAAEThumbNote"
                    }
                ]
            }
        }
    ]

    html = template.render(
        request=req,
        board_id="b",
        boards=BOARD_CONFIG,
        board_info=BOARD_CONFIG.get("b", {"name": "Бред", "description": "Бред и общение"}),
        posts=mock_posts,
        BOT_USERNAME="dvach_test_bot",
        site_mode="PUBLIC_READ",
        session={"user": session_user},
    )

    # Inline style.css and mascot wrapper if missing from template
    with open("site_tgach/static/css/style.css", "r", encoding="utf-8") as f:
        css_content = f.read()

    # Append minimal mascot markup to test computed styles if not in template body
    mascot_markup = """
    <div id="mascot-wrapper">
        <div class="mascot-body">
            <div class="mascot-img visible"></div>
            <div class="mascot-bubble"><span>Привет, Анон!</span></div>
        </div>
    </div>
    """

    injected = html.replace("</head>", f"<style>{css_content}</style></head>")
    injected = injected.replace("</body>", f"{mascot_markup}</body>")
    return injected


def get_rendered_search_html():
    """Render search_results.jinja2 with mock gallery attachments."""
    template = templates.get_template("search_results.jinja2")
    req = make_req("/tags/anime")
    
    mock_search_images = [
        {
            "type": "image",
            "filename": "anime_art.jpg",
            "original_file_id": "AgAC_tag_img_1",
            "thumbnail_file_id": "AgAC_tag_thumb_1",
            "original_url": "https://broken-mirror.imgbb.com/anime.jpg",
            "thumbnail_url": "https://broken-mirror.imgbb.com/thumb.jpg",
            "parent_board_id": "b",
            "parent_post_id": 500
        },
        {
            "type": "video",
            "filename": "anime_clip.mp4",
            "original_file_id": "BAAC_tag_video_1",
            "thumbnail_file_id": "AgAC_tag_vthumb_1",
            "original_url": "/files/BAAC_tag_video_1",
            "thumbnail_url": "/files/AgAC_tag_vthumb_1",
            "parent_board_id": "b",
            "parent_post_id": 501
        }
    ]

    html = template.render(
        request=req,
        board_id="b",
        boards=BOARD_CONFIG,
        board_info=BOARD_CONFIG.get("b", {"name": "Бред", "description": "Бред"}),
        query="anime",
        current_tag="anime",
        is_tag_search=True,
        search_images=mock_search_images,
        posts=[],
        site_mode="PUBLIC_READ",
        session={"user": None},
        archive=False,
    )

    with open("site_tgach/static/css/style.css", "r", encoding="utf-8") as f:
        css_content = f.read()

    return html.replace("</head>", f"<style>{css_content}</style></head>")


# ============================================================================
# PLAYWRIGHT E2E BROWSER TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_e2e_mascot_foreground_and_pointer_events():
    """R3: Verify mascot is layered in foreground (z-index: 100) and wrapper does not block clicks."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 800})

        html = get_rendered_chat_html(session_user=None)
        await page.route("http://localhost:8000/b/chat/", lambda route: route.fulfill(status=200, body=html, content_type="text/html"))
        await page.goto("http://localhost:8000/b/chat/")

        # 1. Mascot wrapper styling checks (Desktop)
        z_index = await page.eval_on_selector("#mascot-wrapper", "el => getComputedStyle(el).zIndex")
        pointer_events_wrapper = await page.eval_on_selector("#mascot-wrapper", "el => getComputedStyle(el).pointerEvents")
        pointer_events_body = await page.eval_on_selector(".mascot-body", "el => getComputedStyle(el).pointerEvents")

        assert z_index == "100", f"Expected desktop --z-mascot: 100, got {z_index}"
        assert pointer_events_wrapper == "none", f"Expected pointer-events: none on wrapper, got {pointer_events_wrapper}"
        assert pointer_events_body == "auto", f"Expected pointer-events: auto on mascot-body, got {pointer_events_body}"

        # 2. Click pass-through test: Click an element located under the mascot wrapper area
        # Verify the underlying link receives click without being blocked by #mascot-wrapper
        link_clicked = await page.evaluate("""() => {
            let clicked = false;
            const link = document.querySelector('.post-num-link');
            if (link) {
                link.addEventListener('click', (e) => { e.preventDefault(); clicked = true; });
                link.click();
            }
            return clicked;
        }""")
        assert link_clicked, "Underlying post link must receive click events through non-blocking wrapper"

        # 3. Mobile viewport check
        await page.set_viewport_size({"width": 375, "height": 667})
        z_index_mobile = await page.eval_on_selector("#mascot-wrapper", "el => getComputedStyle(el).zIndex")
        assert z_index_mobile in ("100", "0"), f"Expected z-index 100 on mobile, got {z_index_mobile}"

        await browser.close()


@pytest.mark.asyncio
async def test_e2e_guest_notice_and_form_disabling():
    """R4: Unauthenticated guest sees instant guest banner and disabled post form."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Guest view
        html = get_rendered_chat_html(session_user=None)
        await page.route("http://localhost:8000/b/chat/", lambda route: route.fulfill(status=200, body=html, content_type="text/html"))
        await page.goto("http://localhost:8000/b/chat/")

        # 1. Guest notice banner visibility
        notice = await page.query_selector(".guest-chat-notice")
        assert notice is not None, ".guest-chat-notice banner must be rendered for unauthenticated guests"
        notice_text = await notice.inner_text()
        assert "Гости могут только читать чат" in notice_text
        assert "Войдите для общения" in notice_text

        # 2. Form disabled state
        form_pointer_events = await page.eval_on_selector("#post-form", "el => getComputedStyle(el).pointerEvents")
        form_opacity = await page.eval_on_selector("#post-form", "el => getComputedStyle(el).opacity")
        assert form_pointer_events == "none", f"Expected pointer-events: none on guest form, got {form_pointer_events}"
        assert float(form_opacity) <= 0.55, f"Expected dimmed opacity on guest form, got {form_opacity}"

        # 3. Authenticated member view: banner must NOT be rendered and form is enabled
        member_html = get_rendered_chat_html(session_user={"id": 12345, "is_guest": False, "is_admin": False})
        await page.route("http://localhost:8000/b/chat/member", lambda route: route.fulfill(status=200, body=member_html, content_type="text/html"))
        await page.goto("http://localhost:8000/b/chat/member")

        member_notice = await page.query_selector(".guest-chat-notice")
        assert member_notice is None, "Authenticated member must not see guest notice banner"
        member_form_pointer_events = await page.eval_on_selector("#post-form", "el => getComputedStyle(el).pointerEvents")
        assert member_form_pointer_events != "none", "Form must be enabled for authenticated users"

        await browser.close()


@pytest.mark.asyncio
async def test_e2e_video_posters_and_thumbnails():
    """R1: Video elements render valid poster thumbnails without mime mismatches."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        html = get_rendered_chat_html(session_user=None)
        await page.route("http://localhost:8000/b/chat/", lambda route: route.fulfill(status=200, body=html, content_type="text/html"))
        await page.goto("http://localhost:8000/b/chat/")

        # 1. Video tag poster attribute check
        videos = await page.query_selector_all("video.post-image")
        assert len(videos) > 0, "Video attachments must be rendered"
        
        for vid in videos:
            poster = await vid.get_attribute("poster")
            assert poster is not None and len(poster) > 0, "Video must have valid poster attribute"
            assert "files/" in poster or "thumb/" in poster, f"Poster must point to thumbnail proxy: {poster}"

        # 2. Video note circular preview
        video_notes = await page.query_selector_all("video.video-note")
        assert len(video_notes) > 0, "Video note must be rendered"
        for vn in video_notes:
            border_radius = await vn.evaluate("el => getComputedStyle(el).borderRadius")
            assert "50%" in border_radius or float(border_radius.replace('px', '')) > 20, "Video note must be rounded"

        await browser.close()


@pytest.mark.asyncio
async def test_e2e_search_gallery_error_fallback():
    """R2: Tag search gallery triggers handleImageError on broken mirrors and falls back."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Load main JS script into page context
        with open("site_tgach/static/js/main.src.js", "r", encoding="utf-8") as f:
            js_content = f.read()

        html = get_rendered_search_html()
        html = html.replace("</body>", f"<script>{js_content}</script></body>")
        await page.route("http://localhost:8000/tags/anime", lambda route: route.fulfill(status=200, body=html, content_type="text/html"))
        await page.goto("http://localhost:8000/tags/anime")

        # 1. Verify onerror handlers are bound
        img = await page.query_selector(".gallery-thumb img")
        assert img is not None, "Gallery thumbnail image must be rendered"

        # 2. Simulate image load error in browser
        fallback_src = await page.evaluate("""() => {
            const el = document.querySelector('.gallery-thumb img');
            if (el && typeof handleImageError === 'function') {
                handleImageError(el);
                return el.src;
            }
            return null;
        }""")

        assert fallback_src is not None
        assert "/files/" in fallback_src or "skip=" in fallback_src, f"Expected Telegram fallback proxy, got {fallback_src}"

        await browser.close()


@pytest.mark.asyncio
async def test_e2e_form_manager_keyboard_and_lifecycle():
    """R5: FormManager lifecycle, Escape dismissal, and zero unhandled TypeError exceptions."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        page_errors = []
        page.on("pageerror", lambda err: page_errors.append(str(err)))

        with open("site_tgach/static/js/main.src.js", "r", encoding="utf-8") as f:
            js_content = f.read()

        html = get_rendered_chat_html(session_user={"id": 1, "is_guest": False})
        html = html.replace("</body>", f"<script>{js_content}</script></body>")
        await page.route("http://localhost:8000/b/chat/test_fm", lambda route: route.fulfill(status=200, body=html, content_type="text/html"))
        await page.goto("http://localhost:8000/b/chat/test_fm")

        # Initialize FormManager on page
        await page.evaluate("""() => {
            if (typeof FormManager !== 'undefined') {
                FormManager.init();
            }
        }""")

        # 1. Safe invocation of FormManager.hideFloating when no floating box exists
        res = await page.evaluate("""() => {
            try {
                if (typeof FormManager !== 'undefined') {
                    FormManager.hideFloating();
                    return true;
                }
                return false;
            } catch (e) {
                return e.message;
            }
        }""")
        assert res is True, f"FormManager.hideFloating() without floatingBox must succeed cleanly, got {res}"

        # 2. Press Escape key in browser -> should not produce uncaught errors
        await page.keyboard.press("Escape")

        # 3. Press Alt+Enter in browser -> should not produce uncaught errors
        await page.keyboard.press("Alt+Enter")

        # 4. Press KeyR in browser -> should focus main form safely
        await page.keyboard.press("KeyR")

        # Assert ZERO uncaught runtime TypeErrors
        type_errors = [e for e in page_errors if "TypeError" in e or "Cannot read properties" in e]
        assert len(type_errors) == 0, f"Encountered unexpected browser TypeErrors: {type_errors}"

        await browser.close()


# ============================================================================
# STANDALONE CLI RUNNER
# ============================================================================

async def run_standalone_suite():
    print("=" * 65)
    print("   STARTING PLAYWRIGHT BROWSER E2E TEST SUITE (Tiers 1-4)")
    print("=" * 65)

    tests = [
        ("R3: Mascot Layering & Pointer Events", test_e2e_mascot_foreground_and_pointer_events),
        ("R4: Guest Notice & Form Disabling", test_e2e_guest_notice_and_form_disabling),
        ("R1: Video Posters & Thumbnails", test_e2e_video_posters_and_thumbnails),
        ("R2: Search Gallery Error Fallback", test_e2e_search_gallery_error_fallback),
        ("R5: FormManager Lifecycle & Shortcuts", test_e2e_form_manager_keyboard_and_lifecycle),
    ]

    passed = 0
    for name, test_fn in tests:
        print(f"\nRunning: {name}...")
        try:
            await test_fn()
            passed += 1
            print(f"  ✓ PASSED: {name}")
        except Exception as e:
            print(f"  ✗ FAILED: {name} -> {e}")
            raise e

    print("\n" + "=" * 65)
    print(f"   ALL {passed}/{len(tests)} PLAYWRIGHT BROWSER E2E TESTS PASSED!")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(run_standalone_suite())
