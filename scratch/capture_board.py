import asyncio
from playwright.async_api import async_playwright

async def capture_board():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 960})
        page = await context.new_page()
        await page.goto("http://127.0.0.1:8000/b/", wait_until="domcontentloaded")
        await asyncio.sleep(4)
        await page.screenshot(path="scratch/playwright_board_before.png", full_page=True)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(capture_board())
