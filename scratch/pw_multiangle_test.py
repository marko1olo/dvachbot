import sys
import os
import time
import socket
import urllib.request
from playwright.sync_api import sync_playwright

# Force UTF-8 encoding for standard output and error streams
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

BASE_URL = "http://127.0.0.1:8000"
CATALOG_URL = f"{BASE_URL}/b/catalog"
SCRATCH_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scratch"))
CATALOG_PNG = os.path.join(SCRATCH_DIR, "pw_catalog.png")
THREAD_PNG = os.path.join(SCRATCH_DIR, "pw_thread.png")

def safe_log(prefix, text):
    try:
        print(f"{prefix} {text}")
    except Exception:
        safe_text = str(text).encode("utf-8", errors="replace").decode("utf-8")
        print(f"{prefix} {safe_text}")

def check_server():
    safe_log("[*]", f"Checking if server is reachable at {BASE_URL}...")
    try:
        req = urllib.request.urlopen(f"{BASE_URL}/healthz", timeout=3)
        if req.getcode() == 200:
            safe_log("[+]", "Server is UP and healthy.")
            return True
    except Exception:
        try:
            req = urllib.request.urlopen(f"{BASE_URL}/b/", timeout=3)
            if req.getcode() == 200:
                safe_log("[+]", "Server is UP.")
                return True
        except Exception as e:
            safe_log("[-]", f"Server health check failed: {e}")
            return False
    return False

def main():
    os.makedirs(SCRATCH_DIR, exist_ok=True)

    if not check_server():
        safe_log("[-]", "Error: Local dev server is not running on http://127.0.0.1:8000")
        sys.exit(1)

    console_errors = []
    failed_requests = []
    media_404s = []
    media_responses = []

    def on_console(msg):
        msg_text = str(msg.text)
        if msg.type == "error":
            safe_log("[JS Error]", msg_text)
            console_errors.append(msg_text)
        elif msg.type == "warning":
            safe_log("[JS Warning]", msg_text)

    def on_request_failed(request):
        req_info = f"{request.method} {request.url} -> {request.failure}"
        safe_log("[Request Failed]", req_info)
        failed_requests.append(req_info)

    def on_response(response):
        url = response.url
        status = response.status
        # Monitor media endpoint requests specifically (/files/...)
        if "/files/" in url or url.endswith((".png", ".jpg", ".jpeg", ".gif", ".webm", ".mp4")):
            media_responses.append((url, status))
            if status == 404:
                safe_log("[404 Media Error]", url)
                media_404s.append(url)

    with sync_playwright() as p:
        safe_log("[*]", "Launching Playwright Chromium headless...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 960})
        page = context.new_page()

        page.on("console", on_console)
        page.on("requestfailed", on_request_failed)
        page.on("response", on_response)

        # ----------------------------------------------------
        # Step A: Catalog Navigation
        # ----------------------------------------------------
        safe_log("[*]", f"Step A: Navigating to Thread Catalog ({CATALOG_URL})...")
        res = page.goto(CATALOG_URL, wait_until="domcontentloaded", timeout=30000)
        assert res and res.status == 200, f"Failed to load catalog page: HTTP {res.status if res else 'No response'}"

        page.wait_for_selector(".catalog-item", timeout=15000)
        page.wait_for_timeout(1000)

        # Progressive incremental scroll to trigger loading="lazy" images
        page.evaluate("""
            async () => {
                const totalHeight = document.body.scrollHeight;
                const step = 400;
                for (let y = 0; y < totalHeight; y += step) {
                    window.scrollTo(0, y);
                    await new Promise(r => setTimeout(r, 100));
                }
                window.scrollTo(0, 0);
            }
        """)
        page.wait_for_timeout(1000)

        # Wait for all image elements to complete loading
        page.evaluate("""
            async () => {
                const startTime = Date.now();
                while (Date.now() - startTime < 10000) {
                    const imgs = Array.from(document.querySelectorAll('img')).filter(img => img.src && !img.src.startsWith('data:image/gif'));
                    if (imgs.length > 0 && imgs.every(img => img.complete)) break;
                    await new Promise(r => setTimeout(r, 250));
                }
            }
        """)

        # Verify all target image elements
        catalog_img_statuses = page.evaluate("""
            () => {
                const imgs = Array.from(document.querySelectorAll('img'));
                return imgs.map(img => ({
                    src: img.currentSrc || img.src,
                    complete: img.complete,
                    naturalWidth: img.naturalWidth
                }));
            }
        """)
        for img_info in catalog_img_statuses:
            src = img_info.get("src", "")
            if src and not src.startswith("data:image/gif"):
                assert img_info["complete"], f"Catalog image element not complete: {src}"
                assert img_info["naturalWidth"] > 0, f"Catalog image element naturalWidth is 0: {src}"

        catalog_img_video_count = page.locator("img, video").count()
        safe_log("[+]", f"Catalog page img/video elements count: {catalog_img_video_count}")
        assert catalog_img_video_count > 0, "Catalog page has 0 img/video elements!"

        page.screenshot(path=CATALOG_PNG, full_page=True)
        safe_log("[+]", f"Catalog full-page screenshot saved to: {CATALOG_PNG}")
        assert os.path.exists(CATALOG_PNG) and os.path.getsize(CATALOG_PNG) > 0, "Catalog screenshot is missing or empty!"

        # Extract a valid thread link from catalog DOM
        thread_links = page.locator("a[href*='/b/res/']").all()
        target_thread_url = None
        for link in thread_links:
            href = link.get_attribute("href")
            if href and "/res/" in href and href.endswith(".html"):
                if href.startswith("http"):
                    target_thread_url = href
                else:
                    target_thread_url = f"{BASE_URL}{href}"
                break

        if not target_thread_url:
            safe_log("[!]", "Could not locate thread link in DOM, fallback to active thread ID from catalog API...")
            import json
            req = urllib.request.urlopen(f"{BASE_URL}/b/catalog.json")
            cat_data = json.loads(req.read().decode("utf-8"))
            threads = cat_data.get("threads", [])
            assert len(threads) > 0, "No threads found in catalog.json!"
            thread_num = threads[0].get("num")
            target_thread_url = f"{BASE_URL}/b/res/{thread_num}.html"

        safe_log("[*]", f"Target thread URL selected: {target_thread_url}")

        # ----------------------------------------------------
        # Step B: Thread Navigation
        # ----------------------------------------------------
        safe_log("[*]", f"Step B: Navigating to Thread ({target_thread_url})...")
        t_res = page.goto(target_thread_url, wait_until="domcontentloaded", timeout=30000)
        assert t_res and t_res.status == 200, f"Failed to load thread page: HTTP {t_res.status if t_res else 'No response'}"

        page.wait_for_timeout(1000)

        # Progressive incremental scroll to trigger loading="lazy" images
        page.evaluate("""
            async () => {
                const totalHeight = document.body.scrollHeight;
                const step = 400;
                for (let y = 0; y < totalHeight; y += step) {
                    window.scrollTo(0, y);
                    await new Promise(r => setTimeout(r, 100));
                }
                window.scrollTo(0, 0);
            }
        """)
        page.wait_for_timeout(1000)

        # Wait for all image elements to complete loading
        page.evaluate("""
            async () => {
                const startTime = Date.now();
                while (Date.now() - startTime < 10000) {
                    const imgs = Array.from(document.querySelectorAll('img')).filter(img => img.src && !img.src.startsWith('data:image/gif'));
                    if (imgs.length > 0 && imgs.every(img => img.complete)) break;
                    await new Promise(r => setTimeout(r, 250));
                }
            }
        """)

        # Verify all target image elements
        thread_img_statuses = page.evaluate("""
            () => {
                const imgs = Array.from(document.querySelectorAll('img'));
                return imgs.map(img => ({
                    src: img.currentSrc || img.src,
                    complete: img.complete,
                    naturalWidth: img.naturalWidth
                }));
            }
        """)
        for img_info in thread_img_statuses:
            src = img_info.get("src", "")
            if src and not src.startswith("data:image/gif"):
                assert img_info["complete"], f"Thread image element not complete: {src}"
                assert img_info["naturalWidth"] > 0, f"Thread image element naturalWidth is 0: {src}"

        thread_img_video_count = page.locator("img, video").count()
        safe_log("[+]", f"Thread page img/video elements count: {thread_img_video_count}")
        assert thread_img_video_count > 0, "Thread page has 0 img/video elements!"

        page.screenshot(path=THREAD_PNG, full_page=True)
        safe_log("[+]", f"Thread full-page screenshot saved to: {THREAD_PNG}")
        assert os.path.exists(THREAD_PNG) and os.path.getsize(THREAD_PNG) > 0, "Thread screenshot is missing or empty!"

        browser.close()

    # ----------------------------------------------------
    # Step C: Network & Console Assertions
    # ----------------------------------------------------
    safe_log("\n---", "Step C: Network & Console Assertions ---")
    safe_log("Total media responses tracked:", len(media_responses))
    safe_log("Media 404 count:", len(media_404s))
    safe_log("Total failed requests count:", len(failed_requests))

    media_failed_requests = [
        r for r in failed_requests 
        if ("/files/" in r or any(ext in r.lower() for ext in [".png", ".jpg", ".jpeg", ".gif", ".webm", ".mp4", ".mov", ".webp"]))
        and "net::ERR_ABORTED" not in r
    ]
    safe_log("Media network request failures count:", len(media_failed_requests))
    safe_log("Uncaught JS console errors count:", len(console_errors))

    # Assert ZERO failed media network requests
    assert len(media_failed_requests) == 0, f"Found failed media network requests: {media_failed_requests}"

    # Filter out non-uncaught / mascot data logs
    app_uncaught_errors = [e for e in console_errors if "Uncaught" in e or "TypeError" in e or "ReferenceError" in e or "SyntaxError" in e]
    safe_log("Application uncaught JS errors count:", len(app_uncaught_errors))

    assert len(app_uncaught_errors) == 0, f"Found uncaught JS exceptions: {app_uncaught_errors}"

    safe_log("\n✅", "Multi-Angle Playwright Simulation PASSED cleanly!")
    safe_log("  - Catalog Screenshot:", f"{CATALOG_PNG} ({os.path.getsize(CATALOG_PNG)} bytes)")
    safe_log("  - Thread Screenshot: ", f"{THREAD_PNG} ({os.path.getsize(THREAD_PNG)} bytes)")

if __name__ == "__main__":
    main()
