import asyncio
from playwright.async_api import async_playwright

JS_ANALYZE = """() => {
    const videos = document.querySelectorAll('.catalog-thumb video.lazy-load');
    const info = [];
    for (const v of Array.from(videos).slice(0, 10)) {
        const wrapper = v.closest('.lazy-media-wrapper');
        const placeholder = wrapper ? wrapper.querySelector('div[style*="background:hsl"]') : null;
        const placeholderDiv = wrapper ? wrapper.querySelector('div[style*="position:absolute"]') : null;
        info.push({
            dataSrc: v.dataset.src ? v.dataset.src.substring(0, 40) : null,
            src: v.src ? v.src.substring(0, 40) : '',
            poster: v.poster ? v.poster.substring(0, 40) : '',
            readyState: v.readyState,
            hasColorPlaceholder: !!placeholder,
            hasAbsPlaceholder: !!placeholderDiv,
            videoZIndex: window.getComputedStyle(v).zIndex,
            videoPos: window.getComputedStyle(v).position,
        });
    }
    return {count: videos.length, items: info};
}"""

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        await page.goto("http://127.0.0.1:8000/b/catalog", wait_until="networkidle", timeout=20000)
        await page.wait_for_timeout(1000)
        
        result = await page.evaluate(JS_ANALYZE)
        print("Video count:", result["count"])
        for i, item in enumerate(result["items"]):
            print(f"  [{i}] poster={item['poster']!r} hasColorPlaceholder={item['hasColorPlaceholder']} hasAbsPlaceholder={item['hasAbsPlaceholder']} videoZ={item['videoZIndex']} readyState={item['readyState']}")
        
        await browser.close()

asyncio.run(main())
