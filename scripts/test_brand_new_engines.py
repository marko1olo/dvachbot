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

from japanese_translator import fetch_nekobot_nsfw, fetch_4chan_live_image
from media_utils import _download_image_with_proxy

SAMPLE_DIR = r"C:\Users\danat\.gemini\antigravity\brain\bb9002fc-4860-4e2b-86f2-07f2a02f02fc\sample_brand_new"
GALLERY_FILE = r"C:\Users\danat\.gemini\antigravity\brain\bb9002fc-4860-4e2b-86f2-07f2a02f02fc\brand_new_engines_gallery.md"
os.makedirs(SAMPLE_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

async def run_brand_new_engine_audit():
    print("=" * 75, flush=True)
    print("✨ [BRAND NEW ANIME & HENTAI ENGINES AUDIT] ✨", flush=True)
    print("   1. NekoBot Explicit API Engine (Hentai, Paizuri, 4K, GIF)")
    print("   2. 4chan Live Imageboard Engine (/h/ Hentai, /e/ Ecchi, /u/ Yuri)")
    print("=" * 75, flush=True)

    results = []

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        # 1. NEKOBOT TESTS
        nekobot_categories = [
            ("Hentai Hardcore", "hentai", "01_nekobot_hentai"),
            ("Paizuri / Tits", "paizuri", "02_nekobot_paizuri"),
            ("Anime Neko Lewd", "hneko", "03_nekobot_hneko"),
            ("Anime Thighs Lewd", "hthigh", "04_nekobot_hthigh"),
            ("4K Ultra High-Res", "4k", "05_nekobot_4k"),
        ]

        print("\n🔮 --- TESTING ENGINE 1: NEKOBOT EXPLICIT API ---", flush=True)
        for label, ntype, prefix in nekobot_categories:
            t0 = time.time()
            print(f"\n[+] Fetching NekoBot ({label})...", flush=True)
            u = await fetch_nekobot_nsfw(session, HEADERS, ntype=ntype)
            fetch_sec = time.time() - t0
            if u:
                print(f"    ✅ URL ({fetch_sec:.2f}s): {u[:70]}...", flush=True)
                t_dl = time.time()
                res = await _download_image_with_proxy(u, timeout=15)
                dl_sec = time.time() - t_dl
                if res and res[0]:
                    raw_bytes = res[0]
                    ext = u.split('.')[-1].split('?')[0].lower()
                    if len(ext) > 4 or ext not in ('jpg', 'jpeg', 'png', 'webp', 'gif', 'mp4'):
                        ext = 'jpg'
                    fname = f"{prefix}.{ext}"
                    fpath = os.path.join(SAMPLE_DIR, fname)
                    dims = "N/A"
                    try:
                        with Image.open(io.BytesIO(raw_bytes)) as img:
                            dims = f"{img.width}x{img.height}"
                    except Exception:
                        pass
                    with open(fpath, "wb") as f:
                        f.write(raw_bytes)
                    size_kb = len(raw_bytes) / 1024
                    print(f"    💾 Saved: {fname} [{dims}, {size_kb:.1f} KB in {dl_sec:.2f}s]", flush=True)
                    results.append({
                        "engine": "NekoBot API",
                        "category": label,
                        "url": u,
                        "filename": fname,
                        "filepath": fpath,
                        "dims": dims,
                        "size_kb": size_kb,
                        "time_sec": fetch_sec + dl_sec
                    })

        # 2. 4CHAN LIVE IMAGEBOARD TESTS
        chan_boards = [
            ("4chan /h/ — Live Hentai Board", "h", "06_4chan_h_live"),
            ("4chan /e/ — Live Ecchi Board", "e", "07_4chan_e_live"),
            ("4chan /u/ — Live Yuri Board", "u", "08_4chan_u_live"),
            ("4chan /c/ — Live Cute/Lewd Board", "c", "09_4chan_c_live"),
        ]

        print("\n🍀 --- TESTING ENGINE 2: 4CHAN LIVE IMAGEBOARD SCRAPER ---", flush=True)
        for label, board, prefix in chan_boards:
            t0 = time.time()
            print(f"\n[+] Fetching {label}...", flush=True)
            u = await fetch_4chan_live_image(session, HEADERS, board=board)
            fetch_sec = time.time() - t0
            if u:
                print(f"    ✅ URL ({fetch_sec:.2f}s): {u[:70]}...", flush=True)
                t_dl = time.time()
                res = await _download_image_with_proxy(u, timeout=15)
                dl_sec = time.time() - t_dl
                if res and res[0]:
                    raw_bytes = res[0]
                    ext = u.split('.')[-1].split('?')[0].lower()
                    if len(ext) > 4 or ext not in ('jpg', 'jpeg', 'png', 'webp', 'gif', 'mp4'):
                        ext = 'jpg'
                    fname = f"{prefix}.{ext}"
                    fpath = os.path.join(SAMPLE_DIR, fname)
                    dims = "N/A"
                    try:
                        with Image.open(io.BytesIO(raw_bytes)) as img:
                            dims = f"{img.width}x{img.height}"
                    except Exception:
                        pass
                    with open(fpath, "wb") as f:
                        f.write(raw_bytes)
                    size_kb = len(raw_bytes) / 1024
                    print(f"    💾 Saved: {fname} [{dims}, {size_kb:.1f} KB in {dl_sec:.2f}s]", flush=True)
                    results.append({
                        "engine": "4chan Live",
                        "category": label,
                        "url": u,
                        "filename": fname,
                        "filepath": fpath,
                        "dims": dims,
                        "size_kb": size_kb,
                        "time_sec": fetch_sec + dl_sec
                    })

    # Generate Gallery Markdown
    gallery_lines = [
        "# ✨ Brand New Anime & Hentai Engines Gallery",
        "",
        f"> **Generated at:** {time.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"> **Total Live Assets Verified:** {len(results)}",
        "",
        "### 📊 Verified Live Engines & Sample Images",
        "",
        "| Engine | Category | Resolution | File Size | Speed | Local Link |",
        "|---|---|---|---|---|---|"
    ]

    for r in results:
        norm_path = r['filepath'].replace('\\', '/')
        gallery_lines.append(f"| **{r['engine']}** | {r['category']} | `{r['dims']}` | `{r['size_kb']:.1f} KB` | `{r['time_sec']:.2f}s` | [{r['filename']}](file:///{norm_path}) |")

    gallery_lines.append("\n### 🖼️ Interactive Image Carousel (Full Live Preview)\n")
    gallery_lines.append("````carousel")
    for idx, r in enumerate(results):
        norm_path = r['filepath'].replace('\\', '/')
        if idx > 0:
            gallery_lines.append("<!-- slide -->")
        gallery_lines.append(f"![{r['category']}](file:///{norm_path})\n*{r['engine']} ({r['category']}) — {r['dims']} ({r['size_kb']:.1f} KB)*")
    gallery_lines.append("````")

    with open(GALLERY_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(gallery_lines))

    print("\n" + "=" * 75, flush=True)
    print(f"🎉 AUDIT COMPLETE: {len(results)} brand new engine assets verified & saved!", flush=True)
    print(f"📁 Gallery: {GALLERY_FILE}", flush=True)
    print("=" * 75, flush=True)

if __name__ == "__main__":
    asyncio.run(run_brand_new_engine_audit())
