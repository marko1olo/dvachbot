import sys
import time
from playwright.sync_api import sync_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 960})
    
    page.goto("http://127.0.0.1:8000/b/catalog", wait_until="domcontentloaded")
    page.wait_for_selector(".catalog-item")

    # Scroll down step-by-step
    page.evaluate("""async () => {
        const totalHeight = document.body.scrollHeight;
        let distance = 800;
        let scrolled = 0;
        while (scrolled < totalHeight) {
            window.scrollBy(0, distance);
            scrolled += distance;
            await new Promise(r => setTimeout(r, 150));
        }
    }""")
    
    # Wait for all image network idle / completes
    page.wait_for_load_state("networkidle")
    time.sleep(2)

    imgs = page.evaluate("""() => Array.from(document.querySelectorAll("img")).map((i, idx) => ({
        idx,
        src: i.src,
        complete: i.complete,
        naturalWidth: i.naturalWidth
    }))""")

    incomplete = [i for i in imgs if i['src'] and not i['src'].startswith("data:image/gif") and (not i['complete'] or i['naturalWidth'] == 0)]
    print(f"Total imgs: {len(imgs)}, Incomplete after networkidle: {len(incomplete)}")
    for i in incomplete:
        print(f"  Incomplete [{i['idx']}]: complete={i['complete']} nW={i['naturalWidth']} src={i['src'][:80]}")

    browser.close()
