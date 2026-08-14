"""
FreeImage.host / iili.io upload module.
API key can be set in .env: FREEIMAGE_API_KEY=...
"""
import httpx
import os
import logging
import asyncio

logger = logging.getLogger("freeimage")

# API key from freeimage.host (get from account settings)
FREEIMAGE_API_KEY = os.getenv("FREEIMAGE_API_KEY", "")

# Proxy config
raw_proxy = os.getenv("PROXY_URL")
PROXY_URL = raw_proxy if raw_proxy and "://" in raw_proxy else (f"http://{raw_proxy}" if raw_proxy else None)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
]


async def upload_file_to_freeimage(file_path: str) -> str | None:
    """
    Uploads a file to freeimage.host / iili.io.
    Returns the direct image URL or None on failure.
    """
    if not os.path.exists(file_path):
        logger.error(f"FreeImage: File not found: {file_path}")
        return None

    url = "https://freeimage.host/api/1/upload"

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


                fname = os.path.basename(file_path)
                data = {"key": FREEIMAGE_API_KEY, "action": "upload", "format": "json"}
                files = {"source": (fname, file_bytes)}

                resp = await client.post(url, data=data, files=files)

                if resp.status_code == 200:
                    j = resp.json()
                    # Response: {"status_code": 200, "success": {"message": "image uploaded"}, "image": {"url": "...", "display_url": "...", ...}}
                    direct_url = (j.get("image") or {}).get("url") or (j.get("image") or {}).get("display_url")
                    if direct_url:
                        logger.info(f"✅ FreeImage upload success ({strategy['name']}): {direct_url}")
                        return direct_url
                    else:
                        logger.warning(f"⚠️ FreeImage: Unexpected response: {resp.text[:300]}")
                else:
                    logger.warning(f"❌ FreeImage ({strategy['name']}): HTTP {resp.status_code}: {resp.text[:200]}")

        except (httpx.ConnectError, httpx.ProxyError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
            logger.warning(f"⚠️ FreeImage {strategy['name']} network error: {repr(e)}")
            await asyncio.sleep(1)
            continue
        except Exception as e:
            logger.error(f"⛔ FreeImage unexpected error ({strategy['name']}): {repr(e)}")
            break

    return None
