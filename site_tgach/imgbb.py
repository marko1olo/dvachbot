"""
ImgBB upload module with multi-key rotating pool and automatic fallback.
Supports images only (jpg, png, gif, bmp, webp). Max 32MB.
"""
import httpx
import os
import logging
import asyncio
import base64
import itertools

logger = logging.getLogger("imgbb")

# Verified active multi-account rotating pool
IMGBB_KEY_POOL = [
    "680574ea1c32adeb15405f2caf0cf899",
    "8416e733b4e086f2b1a5604ad8b8be72",
    "1d26080cc4d0cb4fbb655c71d71a4cc8",
    "bd9ed6c27f06d3ab3f93754b0a4317d7",
    "b0bcf8a3dbd2689b209844f3ee8fc2d9",
    "681a89036c6279ebfc3eee2b1680b6e1"
]

# If custom key in .env, prepend it
_env_key = os.getenv("IMGBB_API_KEY")
if _env_key and _env_key not in IMGBB_KEY_POOL:
    IMGBB_KEY_POOL.insert(0, _env_key)

_key_cycler = itertools.cycle(IMGBB_KEY_POOL)
IMGBB_API_KEY = IMGBB_KEY_POOL[0]

def get_next_imgbb_key() -> str:
    return next(_key_cycler)

raw_proxy = os.getenv("PROXY_URL")
PROXY_URL = raw_proxy if raw_proxy and "://" in raw_proxy else (f"http://{raw_proxy}" if raw_proxy else None)

# Supported formats
IMGBB_SUPPORTED_EXT = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif"}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
]


async def upload_file_to_imgbb(file_path: str) -> str | None:
    """
    Uploads an image file to imgbb.com with rotating key fallback.
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
    fname = os.path.basename(file_path)

    # Try up to 3 keys from pool on failure
    for key_attempt in range(min(3, len(IMGBB_KEY_POOL))):
        current_key = get_next_imgbb_key()

        for strategy in strategies:
            try:
                transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0", retries=2)
                async with httpx.AsyncClient(
                    timeout=60.0, verify=False,
                    proxy=strategy["proxy"], transport=transport,
                    headers={"User-Agent": USER_AGENTS[key_attempt % len(USER_AGENTS)]}
                ) as client:
                    resp = await client.post(
                        url,
                        data={"key": current_key},
                        files={"image": (fname, file_bytes, "image/jpeg" if ext in ['.jpg', '.jpeg'] else f"image/{ext.lstrip('.')}")}
                    )

                    if resp.status_code == 200:
                        j = resp.json()
                        direct_url = (j.get("data") or {}).get("url") or (j.get("data") or {}).get("display_url")
                        if direct_url:
                            logger.info(f"✅ ImgBB upload success ({strategy['name']}, key={current_key[:8]}...): {direct_url}")
                            return direct_url
                        else:
                            logger.warning(f"⚠️ ImgBB: Unexpected response: {resp.text[:300]}")
                    elif resp.status_code == 400:
                        err_code = resp.json().get('error', {}).get('code')
                        err_msg = resp.json().get('error', {}).get('message', '')
                        logger.warning(f"⚠️ ImgBB key {current_key[:8]}... rejected (code {err_code}: {err_msg}). Rotating key...")
                        break  # Break inner strategy loop to try next key
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
