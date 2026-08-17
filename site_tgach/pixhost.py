"""
Pixhost.to upload module with global rate limiting and per-error cooldowns.
No API key needed. Max 10MB per image.
Supports jpg, png, gif, bmp, webp.
"""
import httpx
import os
import logging
import asyncio
import time

logger = logging.getLogger("pixhost")

raw_proxy = os.getenv("PROXY_URL")
PROXY_URL = raw_proxy if raw_proxy and "://" in raw_proxy else (f"http://{raw_proxy}" if raw_proxy else None)

# Supported formats (no animation/video)
PIXHOST_SUPPORTED_EXT = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
PIXHOST_MAX_MB = 10

# Global rate limiting: min 1s between Pixhost requests
_PIXHOST_MIN_INTERVAL = 1.0
_pixhost_last_request_time: float = 0.0
_pixhost_global_lock = asyncio.Lock()

# Global cooldown: if Pixhost returns 429 or repeated errors, back off
_pixhost_backoff_until: float = 0.0

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
]


async def upload_file_to_pixhost(file_path: str) -> str | None:
    """
    Uploads a file to pixhost.to.
    Returns the direct image URL or None on failure.
    """
    global _pixhost_last_request_time, _pixhost_backoff_until

    if not os.path.exists(file_path):
        logger.error(f"Pixhost: File not found: {file_path}")
        return None

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in PIXHOST_SUPPORTED_EXT:
        logger.info(f"Pixhost: Unsupported format {ext}, skipping")
        return None

    file_size = os.path.getsize(file_path)
    if file_size == 0:
        logger.warning("Pixhost: File is 0 bytes, skipping")
        return None
    if file_size > PIXHOST_MAX_MB * 1024 * 1024:
        logger.info(f"Pixhost: File too large ({file_size / 1024 / 1024:.1f} MB > {PIXHOST_MAX_MB}MB). Skipping.")
        return None

    # Check global backoff
    remaining_backoff = _pixhost_backoff_until - time.monotonic()
    if remaining_backoff > 0:
        logger.debug(f"⏭️ [Pixhost] Global backoff active ({remaining_backoff:.0f}s left). Skipping upload.")
        return None

    url = "https://api.pixhost.to/images"

    strategies = [{"proxy": None, "name": "Direct"}]
    if PROXY_URL:
        strategies.append({"proxy": PROXY_URL, "name": "Proxy"})

    def _read_bytes():
        with open(file_path, "rb") as f:
            return f.read()

    file_bytes = await asyncio.to_thread(_read_bytes)

    for strategy in strategies:
        try:
            # Global rate limiting
            async with _pixhost_global_lock:
                now = time.monotonic()
                wait = _pixhost_last_request_time + _PIXHOST_MIN_INTERVAL - now
                if wait > 0:
                    await asyncio.sleep(wait)
                _pixhost_last_request_time = time.monotonic()

            transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0", retries=1)
            async with httpx.AsyncClient(
                timeout=60.0, verify=False,
                proxy=strategy["proxy"], transport=transport,
                headers={
                    "User-Agent": USER_AGENTS[0],
                    "Accept": "application/json"
                }
            ) as client:
                fname = os.path.basename(file_path)
                data = {"content_type": "0", "max_th_size": "300"}
                files = {"img": (fname, file_bytes)}

                resp = await client.post(url, data=data, files=files)

                if resp.status_code == 200:
                    j = resp.json()
                    th_url = j.get("th_url", "")
                    if th_url:
                        logger.info(f"✅ Pixhost upload success ({strategy['name']}): {th_url}")
                        return th_url
                    show_url = j.get("show_url", "")
                    if show_url:
                        import re
                        m = re.match(r"https?://(?:www\.)?pixhost\.to/show/([^/]+)/(.+)", show_url)
                        if m:
                            dir_id, filename = m.group(1), m.group(2)
                            direct_url = f"https://img{dir_id}.pixhost.to/images/{dir_id}/{filename}"
                        else:
                            direct_url = show_url
                        logger.info(f"✅ Pixhost upload success ({strategy['name']}): {direct_url}")
                        return direct_url
                    else:
                        logger.warning(f"⚠️ Pixhost: Unexpected response: {resp.text[:300]}")
                elif resp.status_code == 429:
                    _pixhost_backoff_until = time.monotonic() + 120.0
                    logger.warning(f"⚠️ Pixhost rate-limited (429). Global backoff 120s.")
                    return None
                elif resp.status_code in (503, 502, 500):
                    _pixhost_backoff_until = time.monotonic() + 60.0
                    logger.warning(f"⚠️ Pixhost server error ({resp.status_code}). Backoff 60s.")
                    return None
                else:
                    logger.warning(f"❌ Pixhost ({strategy['name']}): HTTP {resp.status_code}: {resp.text[:200]}")

        except (httpx.ConnectError, httpx.ProxyError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
            logger.warning(f"⚠️ Pixhost {strategy['name']} network error: {repr(e)}")
            await asyncio.sleep(2)
            continue
        except Exception as e:
            logger.error(f"⛔ Pixhost unexpected error ({strategy['name']}): {repr(e)}")
            break

    return None
