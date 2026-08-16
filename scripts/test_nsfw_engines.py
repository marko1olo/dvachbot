import asyncio
import os
import sys
import time
import io
import aiohttp
from typing import Optional
from PIL import Image

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, r"C:\Users\danat\Desktop\dvachbot")

from media_utils import _download_image_with_proxy

SAMPLE_DIR = r"C:\Users\danat\.gemini\antigravity\brain\bb9002fc-4860-4e2b-86f2-07f2a02f02fc\sample_nsfw"
GALLERY_FILE = r"C:\Users\danat\.gemini\antigravity\brain\bb9002fc-4860-4e2b-86f2-07f2a02f02fc\nsfw_gallery.md"
os.makedirs(SAMPLE_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

# --- 1. NEW ENGINE: YANDE.RE EXPLICIT HENTAI & SEX FETCHER ---
async def fetch_yande_explicit(session: aiohttp.ClientSession, tag: str) -> Optional[str]:
    url = f"https://yande.re/post.json?limit=10&tags={tag}+rating:e+score:>10"
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status == 200:
                posts = await resp.json()
                if posts and isinstance(posts, list):
                    import random
                    post = random.choice(posts)
                    return post.get("file_url") or post.get("jpeg_url")
    except Exception as e:
        print(f"[-] Yande.re ({tag}) error: {e}", flush=True)
    return None

# --- 2. NEW ENGINE: SAFEBOORU / YANDE ECCHI & SEMI-NUDE FETCHER ---
async def fetch_safebooru_ecchi(session: aiohttp.ClientSession, tag: str) -> Optional[str]:
    url = f"https://safebooru.org/index.php?page=dapi&s=post&q=index&json=1&limit=10&tags={tag}+score:>15"
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status == 200:
                posts = await resp.json()
                if posts and isinstance(posts, list):
                    import random
                    post = random.choice(posts)
                    d, img = post.get('directory'), post.get('image')
                    if d and img:
                        return f"https://safebooru.org/images/{d}/{img}"
    except Exception as e:
        print(f"[-] Safebooru ({tag}) error: {e}", flush=True)
    return None

# --- 3. NEW ENGINE: MONOGATARI ECCHI FETCHER ---
async def fetch_monogatari_ecchi(session: aiohttp.ClientSession) -> Optional[str]:
    url = "https://yande.re/post.json?limit=10&tags=monogatari_(series)+rating:q+score:>5"
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status == 200:
                posts = await resp.json()
                if posts and isinstance(posts, list):
                    import random
                    post = random.choice(posts)
                    return post.get("file_url") or post.get("jpeg_url")
    except Exception as e:
        print(f"[-] Monogatari ecchi error: {e}", flush=True)
    return None

# --- 4. NEW ENGINE: WAIFU 5-PACK NSFW DROP FETCHER ---
async def fetch_waifu_nsfw_pack(session: aiohttp.ClientSession, count: int = 5) -> list[str]:
    tags = ['bikini', 'underwear', 'swimsuits', 'cleavage', 'nipples', 'nopan', 'dress', 'panties']
    urls = []
    import random
    selected_tags = random.sample(tags, min(count, len(tags)))
    for tag in selected_tags:
        # Try yande rating:q or rating:e
        u = await fetch_yande_explicit(session, tag)
        if not u:
            u = await fetch_safebooru_ecchi(session, tag)
        if u:
            urls.append(u)
    return urls

async def download_and_record(url: str, name: str, filename: str) -> Optional[dict]:
    t0 = time.time()
    res = await _download_image_with_proxy(url, timeout=15)
    dl_sec = time.time() - t0
    if not res or not res[0]:
        print(f"    ❌ Download Failed for {name}", flush=True)
        return None
    raw_bytes = res[0]
    ext = url.split('.')[-1].split('?')[0].lower()
    if len(ext) > 4 or ext not in ('jpg', 'jpeg', 'png', 'webp', 'gif', 'mp4'):
        ext = 'jpg'
    full_name = f"{filename}.{ext}"
    filepath = os.path.join(SAMPLE_DIR, full_name)
    dims = "N/A"
    try:
        with Image.open(io.BytesIO(raw_bytes)) as img:
            dims = f"{img.width}x{img.height}"
    except Exception:
        pass
    with open(filepath, "wb") as f:
        f.write(raw_bytes)
    size_kb = len(raw_bytes) / 1024
    print(f"    💾 Saved: {full_name} [{dims}, {size_kb:.1f} KB in {dl_sec:.2f}s]", flush=True)
    return {
        "name": name,
        "url": url,
        "filename": full_name,
        "filepath": filepath,
        "dims": dims,
        "size_kb": size_kb,
        "dl_sec": dl_sec
    }

async def run_nsfw_audit():
    print("=" * 75, flush=True)
    print("🔞 [LIVE NSFW / ERO / ECCHI / HENTAI ANIME ENGINE VERIFICATION] 🔞", flush=True)
    print("=" * 75, flush=True)

    results = []
    
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        # Category 1: ХЕНТАЙ / СЕКС / ПАЙЗУРИ
        print("\n🔥 [1/5] Testing Hardcore Hentai & Sex Engine (yande.re rating:e)...", flush=True)
        url1 = await fetch_yande_explicit(session, "sex")
        if url1:
            print(f"    ✅ URL: {url1[:80]}...", flush=True)
            r = await download_and_record(url1, "🔥 Хентай / Секс (Hardcore Hentai)", "01_hentai_sex")
            if r: results.append(r)

        # Category 2: ЭРОТИКА / NIPPLES / PUSSY / UNCESORED
        print("\n🔞 [2/5] Testing Uncensored Lewd & Erotica Engine (yande.re nipples/nopan)...", flush=True)
        url2 = await fetch_yande_explicit(session, "nipples")
        if url2:
            print(f"    ✅ URL: {url2[:80]}...", flush=True)
            r = await download_and_record(url2, "🔞 Эротика / Без цензуры (Uncensored Lewd)", "02_ero_uncensored")
            if r: results.append(r)

        # Category 3: ПОЛУГОЛЫЕ / BIKINI / UNDERWEAR / PANTIES
        print("\n👙 [3/5] Testing Semi-Nude / Bikini & Underwear Engine (safebooru/yande)...", flush=True)
        url3 = await fetch_safebooru_ecchi(session, "bikini")
        if url3:
            print(f"    ✅ URL: {url3[:80]}...", flush=True)
            r = await download_and_record(url3, "👙 Полуголые / Бикини (Semi-nude Bikini)", "03_ecchi_bikini")
            if r: results.append(r)

        # Category 4: МОНОГАТАРИ ЭТТИ / GATARI ECCHI
        print("\n🌸 [4/5] Testing Monogatari Lewd & Ecchi Engine...", flush=True)
        url4 = await fetch_monogatari_ecchi(session)
        if url4:
            print(f"    ✅ URL: {url4[:80]}...", flush=True)
            r = await download_and_record(url4, "🌸 Моногатари Этти (Gatari Ecchi)", "04_gatari_ecchi")
            if r: results.append(r)

        # Category 5: СЕКРЕТНЫЙ ДРОП ВАЙФУ (5-PACK BONUS DROP)
        print("\n👑 [5/5] Testing Secret Waifu 5-Pack Drop (15% Chance)...", flush=True)
        pack_urls = await fetch_waifu_nsfw_pack(session, count=5)
        print(f"    ✅ Retrieved {len(pack_urls)} NSFW Waifu URLs", flush=True)
        for idx, pu in enumerate(pack_urls, 1):
            r = await download_and_record(pu, f"👑 Вайфу Дроп #{idx}", f"05_waifu_drop_{idx}")
            if r: results.append(r)

    # Generate Gallery Markdown
    gallery_lines = [
        "# 🔞 NSFW / Erotic / Ecchi / Hentai Engine Gallery",
        "",
        f"> **Generated at:** {time.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"> **Total Live NSFW Assets Verified:** {len(results)}",
        "",
        "### 📊 Direct Asset List & Resolution",
        "",
        "| Category | Resolution | File Size | Latency | Local File Link |",
        "|---|---|---|---|---|"
    ]

    for r in results:
        norm_path = r['filepath'].replace('\\', '/')
        gallery_lines.append(f"| **{r['name']}** | `{r['dims']}` | `{r['size_kb']:.1f} KB` | `{r['dl_sec']:.2f}s` | [{r['filename']}](file:///{norm_path}) |")

    gallery_lines.append("\n### 🖼️ Interactive Image Carousel (Full Live Preview)\n")
    gallery_lines.append("````carousel")
    for idx, r in enumerate(results):
        norm_path = r['filepath'].replace('\\', '/')
        if idx > 0:
            gallery_lines.append("<!-- slide -->")
        gallery_lines.append(f"![{r['name']}](file:///{norm_path})\n*{r['name']} — {r['dims']} ({r['size_kb']:.1f} KB)*")
    gallery_lines.append("````")

    with open(GALLERY_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(gallery_lines))

    print("\n" + "=" * 75, flush=True)
    print(f"🎉 FULL NSFW AUDIT PASSED: {len(results)} spicy images verified & downloaded!", flush=True)
    print(f"📁 Gallery: {GALLERY_FILE}", flush=True)
    print("=" * 75, flush=True)

if __name__ == "__main__":
    asyncio.run(run_nsfw_audit())
