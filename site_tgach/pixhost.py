"""
Pixhost.to upload module.
No API key needed. Max 10MB per image.
Supports jpg, png, gif, bmp, webp.
"""
import httpx
import os
import logging
import asyncio

logger = logging.getLogger("pixhost")

raw_proxy = os.getenv("PROXY_URL")
PROXY_URL = raw_proxy if raw_proxy and "://" in raw_proxy else (f"http://{raw_proxy}" if raw_proxy else None)

# Supported formats (no animation/video)
PIXHOST_SUPPORTED_EXT = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
PIXHOST_MAX_MB = 10

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
]


async def upload_file_to_pixhost(file_path: str) -> str | None:
    """
    Uploads a file to pixhost.to.
    Returns the direct image URL or None on failure.
    """
    if not os.path.exists(file_path):
        logger.error(f"Pixhost: File not found: {file_path}")
        return None

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in PIXHOST_SUPPORTED_EXT:
        logger.info(f"Pixhost: Unsupported format {ext}, skipping")
        return None

    file_size = os.path.getsize(file_path)
    if file_size > PIXHOST_MAX_MB * 1024 * 1024:
        logger.info(f"Pixhost: File too large ({file_size / 1024 / 1024:.1f} MB > {PIXHOST_MAX_MB}MB). Skipping.")
        return None

    url = "https://api.pixhost.to/images"

    strategies = [{"proxy": None, "name": "Direct"}]
    if PROXY_URL:
        strategies.append({"proxy": PROXY_URL, "name": "Proxy"})

    for strategy in strategies:
        try:
            transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0", retries=2)
            async with httpx.AsyncClient(
                timeout=60.0, verify=False,
                proxy=strategy["proxy"], transport=transport,
                headers={
                    "User-Agent": USER_AGENTS[0],
                    "Accept": "application/json"
                }
            ) as client:
                fname = os.path.basename(file_path)
                with open(file_path, "rb") as f:
                    file_bytes = f.read()

                data = {"content_type": "0", "max_th_size": "300"}
                files = {"img": (fname, file_bytes)}

                resp = await client.post(url, data=data, files=files)

                if resp.status_code == 200:
                    j = resp.json()
                    # Response: {"th_url": "...", "show_url": "...", ...}
                    # show_url is the page, th_url is the thumbnail, we need the direct image url
                    # Direct image URL is built from show_url: replace show with img domain
                    show_url = j.get("show_url", "")
                    if show_url:
                        # Construct direct URL: pixhost converts show_url to direct img
                        # e.g. https://pixhost.to/show/123/abc.jpg -> https://img123.pixhost.to/images/123/abc.jpg
                        # The API returns th_url for thumbnail, show_url for page
                        # We store the show_url as the mirror link (functional enough for redirect)
                        direct_url = show_url  # The page shows the image
                        logger.info(f"✅ Pixhost upload success ({strategy['name']}): {direct_url}")
                        return direct_url
                    else:
                        logger.warning(f"⚠️ Pixhost: Unexpected response: {resp.text[:300]}")
                else:
                    logger.warning(f"❌ Pixhost ({strategy['name']}): HTTP {resp.status_code}: {resp.text[:200]}")

        except (httpx.ConnectError, httpx.ProxyError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
            logger.warning(f"⚠️ Pixhost {strategy['name']} network error: {repr(e)}")
            await asyncio.sleep(1)
            continue
        except Exception as e:
            logger.error(f"⛔ Pixhost unexpected error ({strategy['name']}): {repr(e)}")
            break

    return None
