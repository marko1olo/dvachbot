import asyncio
import aiohttp
import time
import json
import xml.etree.ElementTree as ET
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

async def test_more_nsfw():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        # 1. TBIB with XML parser
        try:
            t0 = time.time()
            async with session.get("https://tbib.org/index.php?page=dapi&s=post&q=index&limit=5&tags=bikini") as resp:
                text = await resp.text()
                root = ET.fromstring(text)
                posts = root.findall('post')
                if posts:
                    p = posts[0]
                    d, img = p.get('directory'), p.get('image')
                    url = f"https://tbib.org/images/{d}/{img}"
                    print(f"[+] TBIB (XML parsed): OK ({time.time()-t0:.2f}s) -> {url}")
        except Exception as e:
            print(f"[-] TBIB: FAIL ({e})")

        # 2. Rule34 XML parser
        try:
            t0 = time.time()
            async with session.get("https://api.rule34.xxx/index.php?page=dapi&s=post&q=index&limit=5&tags=rating:explicit+score:>20") as resp:
                text = await resp.text()
                root = ET.fromstring(text)
                posts = root.findall('post')
                if posts:
                    url = posts[0].get('file_url')
                    print(f"[+] Rule34 (XML parsed): OK ({time.time()-t0:.2f}s) -> {url}")
        except Exception as e:
            print(f"[-] Rule34: FAIL ({e})")

        # 3. Safebooru (Hot Ecchi tags: bikini, underwear, swimsuit, cleavage, thong)
        for tag in ['bikini', 'underwear', 'swimsuit', 'cleavage', 'panties', 'ass']:
            try:
                t0 = time.time()
                async with session.get(f"https://safebooru.org/index.php?page=dapi&s=post&q=index&json=1&limit=3&tags={tag}+score:>10") as resp:
                    data = await resp.json()
                    if data:
                        d, img = data[0]['directory'], data[0]['image']
                        print(f"[+] Safebooru ({tag}): OK ({time.time()-t0:.2f}s) -> https://safebooru.org/images/{d}/{img}")
            except Exception as e:
                print(f"[-] Safebooru ({tag}): FAIL ({e})")

        # 4. Yande.re Explicit Tags
        for tag in ['sex', 'paizuri', 'fellatio', 'nakadashi', 'nipples', 'pussy', 'nopan']:
            try:
                t0 = time.time()
                async with session.get(f"https://yande.re/post.json?limit=3&tags={tag}+rating:e") as resp:
                    data = await resp.json()
                    if data:
                        u = data[0].get('file_url') or data[0].get('jpeg_url')
                        print(f"[+] Yande.re ({tag}): OK ({time.time()-t0:.2f}s) -> {u}")
            except Exception as e:
                print(f"[-] Yande.re ({tag}): FAIL ({e})")

asyncio.run(test_more_nsfw())
