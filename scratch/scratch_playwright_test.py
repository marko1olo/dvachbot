import asyncio
import json
import os
import sys
from playwright.async_api import async_playwright

async def run_forensics():
    console_logs = []
    js_errors = []
    failed_requests = []
    failed_responses = []

    os.makedirs("scratch", exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 960})
        page = await context.new_page()

        # Listeners
        page.on("console", lambda msg: console_logs.append({
            "type": msg.type,
            "text": msg.text,
            "location": msg.location
        }))
        
        page.on("pageerror", lambda exc: js_errors.append(str(exc)))

        def handle_request_failed(request):
            failure_str = str(request.failure) if request.failure is not None else "Unknown failure"
            failed_requests.append({
                "url": request.url,
                "method": request.method,
                "failure": failure_str
            })

        page.on("requestfailed", handle_request_failed)

        def handle_response(response):
            if response.status >= 400:
                failed_responses.append({
                    "url": response.url,
                    "status": response.status,
                    "status_text": response.status_text
                })

        page.on("response", handle_response)

        target_url = "http://127.0.0.1:8000/b/"
        print(f"Navigating to {target_url}...")
        try:
            res = await page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
            print(f"Main page status: {res.status if res else 'No response'}")
        except Exception as e:
            print(f"Navigation error: {e}")

        # Wait extra time for JS execution and lazy dynamic renders
        await asyncio.sleep(3)

        # Collect post media statistics on board page
        board_images = await page.evaluate("""() => {
            const imgs = Array.from(document.querySelectorAll('img'));
            return imgs.map(img => ({
                src: img.src,
                getAttributeSrc: img.getAttribute('src'),
                complete: img.complete,
                naturalWidth: img.naturalWidth,
                naturalHeight: img.naturalHeight,
                width: img.width,
                height: img.height,
                alt: img.alt,
                className: img.className,
                parentElement: img.parentElement ? img.parentElement.tagName : null,
                outerHTML: img.outerHTML
            }));
        }""")

        board_videos = await page.evaluate("""() => {
            const vids = Array.from(document.querySelectorAll('video'));
            return vids.map(vid => ({
                src: vid.src,
                getAttributeSrc: vid.getAttribute('src'),
                outerHTML: vid.outerHTML
            }));
        }""")

        # Get thread links via JS
        thread_hrefs = await page.evaluate("""() => {
            const links = Array.from(document.querySelectorAll('a[href*="/res/"]'));
            return links.map(a => a.href);
        }""")
        print(f"Found {len(thread_hrefs)} thread links on board page: {thread_hrefs[:3]}")

        # Navigate to first thread if available
        if thread_hrefs:
            first_thread_url = thread_hrefs[0]
            print(f"Navigating to active thread: {first_thread_url}...")
            try:
                await page.goto(first_thread_url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(3)
            except Exception as e:
                print(f"Thread navigation error: {e}")

        # Take full-page screenshot
        screenshot_path = sys.argv[1] if len(sys.argv) > 1 else "scratch/playwright_after.png"
        await page.screenshot(path=screenshot_path, full_page=True)
        print(f"Full-page screenshot saved to {screenshot_path}")

        # Gather final DOM elements audit
        final_images_data = await page.evaluate("""() => {
            const imgs = Array.from(document.querySelectorAll('img'));
            return imgs.map(img => ({
                src: img.src,
                getAttributeSrc: img.getAttribute('src'),
                complete: img.complete,
                naturalWidth: img.naturalWidth,
                naturalHeight: img.naturalHeight,
                width: img.width,
                height: img.height,
                alt: img.alt,
                className: img.className,
                parentElement: img.parentElement ? img.parentElement.tagName : null,
                outerHTML: img.outerHTML
            }));
        }""")

        final_videos_data = await page.evaluate("""() => {
            const vids = Array.from(document.querySelectorAll('video'));
            return vids.map(vid => ({
                src: vid.src,
                getAttributeSrc: vid.getAttribute('src'),
                outerHTML: vid.outerHTML
            }));
        }""")

        report = {
            "target_url": target_url,
            "console_logs": console_logs,
            "js_errors": js_errors,
            "failed_requests": failed_requests,
            "failed_responses": failed_responses,
            "board_images_count": len(board_images),
            "board_images": board_images,
            "board_videos_count": len(board_videos),
            "board_videos": board_videos,
            "final_images_count": len(final_images_data),
            "final_images": final_images_data,
            "final_videos_count": len(final_videos_data),
            "final_videos": final_videos_data
        }

        with open("scratch/playwright_forensics.json", "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        await browser.close()
        return report

if __name__ == "__main__":
    report = asyncio.run(run_forensics())
    print("\n--- FORENSICS SUMMARY ---")
    print(f"JS Errors (Pageerror): {len(report['js_errors'])}")
    for err in report['js_errors']:
        print(f"  - {err}")

    print(f"\nConsole Logs: {len(report['console_logs'])}")
    for log in report['console_logs']:
        if log['type'] in ['error', 'warning'] or '404' in str(log.get('text', '')) or 'Failed' in str(log.get('text', '')) or 'Error' in str(log.get('text', '')):
            try:
                print(f"  [{log['type'].upper()}] {log['text']} @ {log['location']}")
            except Exception:
                print(f"  [{log['type'].upper()}] (non-ascii text) @ {log['location']}")

    print(f"\nFailed Requests (Network error): {len(report['failed_requests'])}")
    for req in report['failed_requests']:
        print(f"  - {req['method']} {req['url']} -> {req['failure']}")

    print(f"\nFailed Responses (HTTP >= 400): {len(report['failed_responses'])}")
    for res in report['failed_responses']:
        print(f"  - HTTP {res['status']} {res['status_text']} -> {res['url']}")

    print(f"\nFinal Images in DOM: {report['final_images_count']}")
    for idx, img in enumerate(report['final_images']):
        try:
            print(f"  Img #{idx+1}: src='{img['src']}' complete={img['complete']} naturalSize={img['naturalWidth']}x{img['naturalHeight']} alt='{img['alt']}' class='{img['className']}' parent={img['parentElement']}")
        except Exception:
            pass

    print(f"\nFinal Videos in DOM: {report['final_videos_count']}")
    for idx, vid in enumerate(report['final_videos']):
        try:
            print(f"  Vid #{idx+1}: src='{vid['src']}' html='{vid['outerHTML']}'")
        except Exception:
            pass

    # Empirical Assertions
    media_404s = [r for r in report['failed_responses'] if '/files/' in r['url'] and r['status'] == 404]
    print(f"\nMedia 404 Requests Count: {len(media_404s)}")
    assert report['final_images_count'] > 0, "No image elements found in DOM!"
    assert len(media_404s) == 0, f"Found {len(media_404s)} HTTP 404 media requests!"
    print("✅ All Playwright empirical assertions PASSED successfully!")
