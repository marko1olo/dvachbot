import asyncio
import aiohttp
import time
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

async def test_extra_boorus():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        # 1. Realbooru
        try:
            t0 = time.time()
            async with session.get("https://realbooru.com/index.php?page=dapi&s=post&q=index&json=1&limit=3&tags=rating:e") as resp:
                data = await resp.json()
                if data:
                    d, img = data[0]['directory'], data[0]['image']
                    print(f"[+] Realbooru: OK ({time.time()-t0:.2f}s) -> https://realbooru.com/images/{d}/{img}")
        except Exception as e:
            print(f"[-] Realbooru: FAIL ({e})")

        # 2. Hypnohub
        try:
            t0 = time.time()
            async with session.get("https://hypnohub.net/index.php?page=dapi&s=post&q=index&json=1&limit=3&tags=rating:e") as resp:
                data = await resp.json()
                if data:
                    d, img = data[0]['directory'], data[0]['image']
                    print(f"[+] Hypnohub: OK ({time.time()-t0:.2f}s) -> https://hypnohub.net/images/{d}/{img}")
        except Exception as e:
            print(f"[-] Hypnohub: FAIL ({e})")

        # 3. Rule34.paheal.net
        try:
            t0 = time.time()
            async with session.get("https://rule34.paheal.net/api/danbooru/find_posts/index.xml?limit=3&tags=anime") as resp:
                print(f"[+] Paheal: Status {resp.status} ({time.time()-t0:.2f}s)")
        except Exception as e:
            print(f"[-] Paheal: FAIL ({e})")

        # 4. Sankaku / Lolibooru
        try:
            t0 = time.time()
            async with session.get("https://lolibooru.moe/post/index.json?limit=3&tags=rating:q") as resp:
                data = await resp.json()
                if data:
                    print(f"[+] Lolibooru: OK ({time.time()-t0:.2f}s) -> {data[0].get('file_url')}")
        except Exception as e:
            print(f"[-] Lolibooru: FAIL ({e})")

asyncio.run(test_extra_boorus())
