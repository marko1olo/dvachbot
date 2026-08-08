import asyncio
from playwright.async_api import async_playwright

async def main():
    loaded_js = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-cache"]
        )
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        
        # Intercept all JS requests
        async def on_request(request):
            if request.resource_type == "script":
                loaded_js.append(request.url)
        
        context.on("request", on_request)
        page = await context.new_page()
        
        await page.goto("http://127.0.0.1:8000/b/catalog", wait_until="networkidle", timeout=25000)
        
        import sys
        sys.stdout.buffer.write(b'Loaded JS files:\n')
        for js in loaded_js:
            sys.stdout.buffer.write((js + '\n').encode('utf-8'))
        sys.stdout.buffer.flush()
        
        await context.close()
        await browser.close()

asyncio.run(main())
