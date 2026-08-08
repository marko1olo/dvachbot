import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        # Force no cache
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-cache", "--disable-application-cache", "--disable-offline-load-stale-cache"]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            ignore_https_errors=True,
        )
        # Bypass cache completely
        await context.route("**/*.js", lambda route: route.continue_(headers={"Cache-Control": "no-cache"}))
        
        page = await context.new_page()
        
        # Force hard reload
        await page.goto("http://127.0.0.1:8000/b/catalog", wait_until="networkidle", timeout=25000)
        await page.wait_for_timeout(3000)
        
        # Verify JS version loaded
        js_size = await page.evaluate("""() => {
            const scripts = document.querySelectorAll('script[src*="main.src.js"]');
            return scripts.length > 0 ? 'found' : 'not found';
        }""")
        print(f"main.src.js script tag: {js_size}")
        
        # Check video wrappers
        result = await page.evaluate("""() => {
            const wrappers = document.querySelectorAll('.catalog-thumb.lazy-media-wrapper');
            const info = [];
            for (const w of Array.from(wrappers).slice(0, 5)) {
                const vid = w.querySelector('video');
                const img = w.querySelector('img');
                const bg = window.getComputedStyle(w).backgroundColor;
                info.push({
                    bg: bg,
                    hasVid: !!vid,
                    hasImg: !!img,
                    vidOpacity: vid ? window.getComputedStyle(vid).opacity : null,
                    vidPoster: vid ? vid.getAttribute('poster') : null,
                    imgSrc: img ? (img.src || '').substring(0, 60) : null,
                    wrapperStyle: w.getAttribute('style') || '',
                });
            }
            return {count: wrappers.length, items: info};
        }""")
        
        print(f"Video wrappers: {result['count']}")
        for i, item in enumerate(result["items"]):
            print(f"  [{i}] bg={item['bg']} hasImg={item['hasImg']} vidPoster={str(item['vidPoster'])[:40] if item['vidPoster'] else 'None'} wrapperBg={item['wrapperStyle'][:60]}")
        
        # Screenshot
        await page.screenshot(path="scratch/catalog_v4.png", full_page=False)
        print("Screenshot: scratch/catalog_v4.png")
        
        await context.close()
        await browser.close()

asyncio.run(main())
