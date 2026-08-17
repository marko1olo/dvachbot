"""
ImgBB upload module with multi-key rotating pool, per-key cooldowns, and global rate limiting.
Supports images only (jpg, png, gif, bmp, webp). Max 32MB.
"""
import httpx
import os
import logging
import asyncio
import time
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

# Per-key cooldown: {key: timestamp_available_again}
_KEY_COOLDOWN: dict[str, float] = {}

# Min seconds between consecutive ImgBB API requests (global rate limit)
_IMGBB_MIN_INTERVAL = 0.5
_imgbb_last_request_time: float = 0.0
_imgbb_global_lock = asyncio.Lock()

# Cooldown duration when a key returns 400 (seconds)
_KEY_COOLDOWN_DURATION = 60.0


def _is_key_available(key: str) -> bool:
    return time.monotonic() >= _KEY_COOLDOWN.get(key, 0.0)


def _cooldown_key(key: str, duration: float = _KEY_COOLDOWN_DURATION):
    _KEY_COOLDOWN[key] = time.monotonic() + duration
    logger.debug(f"[ImgBB] Key {key[:8]}... on cooldown for {duration:.0f}s")


def get_next_imgbb_key() -> str:
    """Return next available key from pool, skipping cooled-down ones."""
    for _ in range(len(IMGBB_KEY_POOL)):
        key = next(_key_cycler)
        if _is_key_available(key):
            return key
    # All keys on cooldown — return next anyway and let caller handle failure
    logger.warning("[ImgBB] All keys are on cooldown! Using next anyway...")
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
    Uploads an image file to imgbb.com with rotating key fallback + rate limiting.
    Returns the direct image URL or None on failure.
    """
    global _imgbb_last_request_time

    if not os.path.exists(file_path):
        logger.error(f"ImgBB: File not found: {file_path}")
        return None

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in IMGBB_SUPPORTED_EXT:
        logger.info(f"ImgBB: Unsupported format {ext}, skipping")
        return None

    file_size = os.path.getsize(file_path)
    if file_size == 0:
        logger.warning("ImgBB: File is 0 bytes, skipping")
        return None
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

    # Try up to all available keys from pool on failure
    n_keys = len(IMGBB_KEY_POOL)
    for key_attempt in range(n_keys):
        current_key = get_next_imgbb_key()

        # If this key is on cooldown and all others are too — bail early
        if not _is_key_available(current_key):
            logger.warning(f"[ImgBB] Key {current_key[:8]}... still on cooldown, skipping attempt {key_attempt+1}")
            continue

        for strategy in strategies:
            try:
                # Global rate limiting: enforce minimum interval between requests
                async with _imgbb_global_lock:
                    now = time.monotonic()
                    wait = _imgbb_last_request_time + _IMGBB_MIN_INTERVAL - now
                    if wait > 0:
                        await asyncio.sleep(wait)
                    _imgbb_last_request_time = time.monotonic()

                transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0", retries=1)
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
                        try:
                            err_code = resp.json().get('error', {}).get('code')
                            err_msg = resp.json().get('error', {}).get('message', '')
                        except Exception:
                            err_code, err_msg = '?', resp.text[:100]
                        logger.warning(f"⚠️ ImgBB key {current_key[:8]}... rejected (code {err_code}: {err_msg}). Cooldown {_KEY_COOLDOWN_DURATION:.0f}s.")
                        _cooldown_key(current_key)
                        break  # Break inner strategy loop to try next key
                    elif resp.status_code == 429:
                        # Rate limit hit — back off this key longer
                        _cooldown_key(current_key, duration=120.0)
                        logger.warning(f"⚠️ ImgBB key {current_key[:8]}... rate-limited (429). Cooldown 120s.")
                        break
                    else:
                        logger.warning(f"❌ ImgBB ({strategy['name']}): HTTP {resp.status_code}: {resp.text[:200]}")

            except (httpx.ConnectError, httpx.ProxyError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                logger.warning(f"⚠️ ImgBB {strategy['name']} network error: {repr(e)}")
                await asyncio.sleep(2)
                continue
            except Exception as e:
                logger.error(f"⛔ ImgBB unexpected error ({strategy['name']}): {repr(e)}")
                break

    return None
