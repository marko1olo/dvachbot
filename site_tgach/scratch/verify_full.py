import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-cache"]
        )
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await context.new_page()
        
        await page.goto("http://127.0.0.1:8000/b/catalog", wait_until="networkidle", timeout=25000)
        await page.wait_for_timeout(2000)
        
        # Scroll through full page to trigger lazy loading
        for scroll_y in [500, 1200, 2000, 3000, 4000, 5000, 6000]:
            await page.evaluate(f"window.scrollTo(0, {scroll_y})")
            await page.wait_for_timeout(400)
        
        await page.wait_for_timeout(1500)
        
        # Check for black backgrounds
        black_count = await page.evaluate("""() => {
            let blacks = 0;
            document.querySelectorAll('.catalog-thumb.lazy-media-wrapper').forEach(w => {
                const bg = window.getComputedStyle(w).backgroundColor;
                if (bg === 'rgb(0, 0, 0)' || bg === 'rgba(0, 0, 0, 1)') blacks++;
            });
            return blacks;
        }""")
        
        total_wrappers = await page.evaluate("document.querySelectorAll('.catalog-thumb.lazy-media-wrapper').length")
        print(f"Total video wrappers: {total_wrappers}")
        print(f"Black backgrounds: {black_count}")
        
        # Full page screenshot
        await page.screenshot(path="scratch/catalog_full.png", full_page=True, clip={"x": 0, "y": 0, "width": 1280, "height": 4000})
        print("Full screenshot: scratch/catalog_full.png")
        
        await context.close()
        await browser.close()

asyncio.run(main())
