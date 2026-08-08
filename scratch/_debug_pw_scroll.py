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

    # Inspect images BEFORE scroll
    imgs_before = page.evaluate("""() => Array.from(document.querySelectorAll("img")).map((i, idx) => ({
        idx,
        src: i.src,
        loading: i.getAttribute("loading"),
        complete: i.complete,
        naturalWidth: i.naturalWidth,
        top: i.getBoundingClientRect().top
    }))""")

    print("--- BEFORE SCROLL ---")
    for i in imgs_before:
        if i["src"] and not i["src"].startswith("data:image/gif"):
            print(f"[{i['idx']}] top={i['top']:.0f} loading={i['loading']} complete={i['complete']} nW={i['naturalWidth']} src={i['src'][:80]}")

    # Scroll down slowly
    page.evaluate("""async () => {
        const distance = 500;
        while (document.documentElement.scrollTop + window.innerHeight < document.documentElement.scrollHeight) {
            window.scrollBy(0, distance);
            await new Promise(r => setTimeout(r, 200));
        }
    }""")
    time.sleep(2)

    imgs_after_scroll_bottom = page.evaluate("""() => Array.from(document.querySelectorAll("img")).map((i, idx) => ({
        idx,
        src: i.src,
        loading: i.getAttribute("loading"),
        complete: i.complete,
        naturalWidth: i.naturalWidth,
        top: i.getBoundingClientRect().top
    }))""")

    print("\n--- AT BOTTOM OF SCROLL ---")
    for i in imgs_after_scroll_bottom:
        if i["src"] and not i["src"].startswith("data:image/gif"):
            print(f"[{i['idx']}] top={i['top']:.0f} loading={i['loading']} complete={i['complete']} nW={i['naturalWidth']} src={i['src'][:80]}")

    browser.close()
