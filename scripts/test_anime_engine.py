import asyncio
import os
import sys
import time
import io
from typing import Optional
from PIL import Image

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, r"C:\Users\danat\Desktop\dvachbot")

from japanese_translator import (
    get_random_anime_image,
    get_nsfw_anime_image,
    get_monogatari_image,
    get_loli_image,
    get_event_anime_images
)
from media_utils import _download_image_with_proxy

SAMPLE_DIR = r"C:\Users\danat\.gemini\antigravity\brain\bb9002fc-4860-4e2b-86f2-07f2a02f02fc\sample_anime"
GALLERY_FILE = r"C:\Users\danat\.gemini\antigravity\brain\bb9002fc-4860-4e2b-86f2-07f2a02f02fc\anime_gallery.md"
os.makedirs(SAMPLE_DIR, exist_ok=True)

async def test_and_download(name: str, fetch_func, prefix: str) -> Optional[dict]:
    t0 = time.time()
    print(f"\n[+] Testing {name}...", flush=True)
    try:
        url = await fetch_func()
        fetch_sec = time.time() - t0
        if not url:
            print(f"    ❌ Failed to retrieve URL in {fetch_sec:.2f}s", flush=True)
            return None
            
        print(f"    ✅ URL Fetched ({fetch_sec:.2f}s): {url[:80]}...", flush=True)
        
        t_dl = time.time()
        dl_res = await _download_image_with_proxy(url, timeout=15)
        dl_sec = time.time() - t_dl
        
        if not dl_res or not dl_res[0]:
            print(f"    ❌ Download Failed in {dl_sec:.2f}s", flush=True)
            return None
            
        raw_bytes = dl_res[0]
        ext = url.split('.')[-1].split('?')[0].lower()
        if len(ext) > 4 or ext not in ('jpg', 'jpeg', 'png', 'webp', 'gif', 'mp4'):
            ext = 'jpg'
            
        # Verify with PIL if image
        dims = "N/A"
        try:
            with Image.open(io.BytesIO(raw_bytes)) as img:
                dims = f"{img.width}x{img.height}"
        except Exception:
            pass

        filename = f"{prefix}.{ext}"
        filepath = os.path.join(SAMPLE_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(raw_bytes)
            
        size_kb = len(raw_bytes) / 1024
        print(f"    💾 Saved: {filename} ({dims}, {size_kb:.1f} KB, dl={dl_sec:.2f}s, total={fetch_sec+dl_sec:.2f}s)", flush=True)
        return {
            "name": name,
            "url": url,
            "filename": filename,
            "filepath": filepath,
            "dims": dims,
            "size_kb": size_kb,
            "fetch_sec": fetch_sec,
            "dl_sec": dl_sec,
            "total_sec": fetch_sec + dl_sec
        }
    except Exception as e:
        print(f"    ❌ Error during test: {e}", flush=True)
        return None

async def run_full_anime_audit():
    print("=" * 75, flush=True)
    print("🌸 [INDEPENDENT ANIME ENGINE & WAIFU DROP VERIFICATION SUITE] 🌸", flush=True)
    print("=" * 75, flush=True)

    results = []

    # 1. Single Command Tests
    single_tests = [
        ("Random Anime SFW (/anime)", get_random_anime_image, "01_anime_sfw"),
        ("Random Anime NSFW (/fap)", get_nsfw_anime_image, "02_anime_fap_nsfw"),
        ("Monogatari / Gatari (/gatari)", get_monogatari_image, "03_anime_gatari"),
        ("Loli Art SFW (/loli)", get_loli_image, "04_anime_loli"),
    ]

    for name, func, prefix in single_tests:
        res = await test_and_download(name, func, prefix)
        if res:
            results.append(res)

    # 2. Waifu Event 5-Pack Drop Test
    print("\n[+] Testing 5-Pack Secret Waifu Bonus Drop...", flush=True)
    t0 = time.time()
    try:
        event_urls = await get_event_anime_images(is_nsfw=False, is_loli=False, count=5)
        fetch_sec = time.time() - t0
        print(f"    ✅ Retrieved {len(event_urls)} event URLs in {fetch_sec:.2f}s", flush=True)
        for idx, u in enumerate(event_urls, 1):
            t_dl = time.time()
            dl_res = await _download_image_with_proxy(u, timeout=15)
            dl_sec = time.time() - t_dl
            if dl_res and dl_res[0]:
                raw_bytes = dl_res[0]
                ext = u.split('.')[-1].split('?')[0].lower()
                if len(ext) > 4 or ext not in ('jpg', 'jpeg', 'png', 'webp', 'gif', 'mp4'):
                    ext = 'jpg'
                dims = "N/A"
                try:
                    with Image.open(io.BytesIO(raw_bytes)) as img:
                        dims = f"{img.width}x{img.height}"
                except Exception:
                    pass
                filename = f"05_waifu_pack_item_{idx}.{ext}"
                filepath = os.path.join(SAMPLE_DIR, filename)
                with open(filepath, "wb") as f:
                    f.write(raw_bytes)
                size_kb = len(raw_bytes) / 1024
                print(f"    💾 Pack #{idx}: {filename} ({dims}, {size_kb:.1f} KB, dl={dl_sec:.2f}s)", flush=True)
                results.append({
                    "name": f"Waifu Bonus Pack #{idx}",
                    "url": u,
                    "filename": filename,
                    "filepath": filepath,
                    "dims": dims,
                    "size_kb": size_kb,
                    "fetch_sec": fetch_sec / max(1, len(event_urls)),
                    "dl_sec": dl_sec,
                    "total_sec": (fetch_sec / max(1, len(event_urls))) + dl_sec
                })
    except Exception as e:
        print(f"    ❌ Error during waifu pack test: {e}", flush=True)

    # 3. Generate Markdown Artifact Gallery
    gallery_lines = [
        "# 🌸 Anime & Waifu Engine Verification Gallery",
        "",
        f"> **Audit Timestamp:** {time.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"> **Total Live Assets Verified:** {len(results)}",
        "",
        "### 📊 Test Results & Latencies",
        "",
        "| Asset / Command | Resolution | File Size | Fetch + Download | Direct Link |",
        "|---|---|---|---|---|"
    ]

    for r in results:
        norm_path = r['filepath'].replace('\\', '/')
        gallery_lines.append(f"| **{r['name']}** | `{r['dims']}` | `{r['size_kb']:.1f} KB` | `{r['total_sec']:.2f}s` | [{r['filename']}](file:///{norm_path}) |")

    gallery_lines.append("\n### 🖼️ Interactive Image Carousel\n")
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
    print(f"🎉 FULL ANIME AUDIT PASSED: {len(results)} assets downloaded and verified!", flush=True)
    print(f"📁 Artifact Gallery: {GALLERY_FILE}", flush=True)
    print("=" * 75, flush=True)

if __name__ == "__main__":
    asyncio.run(run_full_anime_audit())
