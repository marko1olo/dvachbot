import sys
import time
from playwright.sync_api import sync_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 960})
    
    responses = {}
    
    def on_resp(r):
        responses[r.url] = r.status
        if r.status != 200:
            print(f"[RESP {r.status}] {r.url[:120]}")

    page.on("response", on_resp)
    page.on("requestfailed", lambda r: print(f"[FAILED] {r.url[:120]} -> {r.failure}"))
    page.on("console", lambda m: print(f"[CONSOLE {m.type}] {m.text[:120]}"))

    print("Navigating to catalog...")
    page.goto("http://127.0.0.1:8000/b/catalog", wait_until="domcontentloaded")
    page.wait_for_selector(".catalog-item")
    
    print("Scrolling to bottom...")
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(3)
    print("Scrolling to top...")
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(2)

    imgs = page.evaluate("""() => Array.from(document.querySelectorAll("img")).map(i => ({
        src: i.src,
        datasetSrc: i.dataset.src,
        complete: i.complete,
        naturalWidth: i.naturalWidth,
        naturalHeight: i.naturalHeight
    }))""")

    incomplete_imgs = [i for i in imgs if i['src'] and not i['src'].startswith("data:image/gif") and (not i['complete'] or i['naturalWidth'] == 0)]
    print(f"\nTotal imgs: {len(imgs)}, Incomplete/Broken imgs: {len(incomplete_imgs)}")
    for i in incomplete_imgs:
        url = i['src']
        status = responses.get(url, "NO_RESP_TRACKED")
        print(f"URL: {url}\n  Status in browser: {status}, complete: {i['complete']}, naturalWidth: {i['naturalWidth']}")

    browser.close()
