"""
ImgBB upload module.
API key: https://api.imgbb.com/ -> get key from account
Set in .env: IMGBB_API_KEY=...
Supports images only (jpg, png, gif, bmp, webp). Max 32MB.
"""
import httpx
import os
import logging
import asyncio
import base64

logger = logging.getLogger("imgbb")

IMGBB_API_KEY = os.getenv("IMGBB_API_KEY") or "680574ea1c32adeb15405f2caf0cf899"

raw_proxy = os.getenv("PROXY_URL")
PROXY_URL = raw_proxy if raw_proxy and "://" in raw_proxy else (f"http://{raw_proxy}" if raw_proxy else None)

# Supported formats
IMGBB_SUPPORTED_EXT = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif"}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
]


async def upload_file_to_imgbb(file_path: str) -> str | None:
    """
    Uploads an image file to imgbb.com.
    Returns the direct image URL or None on failure.
    """
    if not os.path.exists(file_path):
        logger.error(f"ImgBB: File not found: {file_path}")
        return None

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in IMGBB_SUPPORTED_EXT:
        logger.info(f"ImgBB: Unsupported format {ext}, skipping")
        return None

    file_size = os.path.getsize(file_path)
    if file_size > 32 * 1024 * 1024:
        logger.info(f"ImgBB: File too large ({file_size / 1024 / 1024:.1f} MB), max 32MB. Skipping.")
        return None

    url = "https://api.imgbb.com/1/upload"

    strategies = [{"proxy": None, "name": "Direct"}]
    if PROXY_URL:
        strategies.append({"proxy": PROXY_URL, "name": "Proxy"})

    def _read_bytes():
        with open(file_path, "rb") as f:
            return f.read()

    file_bytes = await asyncio.to_thread(_read_bytes)
    for strategy in strategies:
        try:
            transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0", retries=2)
            async with httpx.AsyncClient(
                timeout=60.0, verify=False,
                proxy=strategy["proxy"], transport=transport,
                headers={"User-Agent": USER_AGENTS[0]}
            ) as client:
                # ImgBB accepts base64 encoded image
                image_b64 = base64.b64encode(file_bytes).decode("utf-8")

                data = {"key": IMGBB_API_KEY, "image": image_b64}

                resp = await client.post(url, data=data)

                if resp.status_code == 200:
                    j = resp.json()
                    # Response: {"data": {"url": "...", "display_url": "...", ...}, "success": true, ...}
                    direct_url = (j.get("data") or {}).get("url") or (j.get("data") or {}).get("display_url")
                    if direct_url:
                        logger.info(f"✅ ImgBB upload success ({strategy['name']}): {direct_url}")
                        return direct_url
                    else:
                        logger.warning(f"⚠️ ImgBB: Unexpected response: {resp.text[:300]}")
                elif resp.status_code == 400:
                    logger.warning(f"❌ ImgBB: Bad request (likely wrong API key or bad image): {resp.text[:200]}")
                    return None  # Don't retry on bad request
                else:
                    logger.warning(f"❌ ImgBB ({strategy['name']}): HTTP {resp.status_code}: {resp.text[:200]}")

        except (httpx.ConnectError, httpx.ProxyError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
            logger.warning(f"⚠️ ImgBB {strategy['name']} network error: {repr(e)}")
            await asyncio.sleep(1)
            continue
        except Exception as e:
            logger.error(f"⛔ ImgBB unexpected error ({strategy['name']}): {repr(e)}")
            break

    return None
