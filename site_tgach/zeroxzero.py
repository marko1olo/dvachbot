import asyncio
import logging
import os
import random
import time
from pathlib import Path

import httpx

logger = logging.getLogger("zeroxzero")

ZEROXZERO_ENDPOINT = os.getenv("ZEROXZERO_ENDPOINT", "https://0x0.st")
ZEROXZERO_ENABLED = os.getenv("ZEROXZERO_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}
ZEROXZERO_MAX_BYTES = int(os.getenv("ZEROXZERO_MAX_BYTES", str(512 * 1024 * 1024)))
ZEROXZERO_COOLDOWN_SECONDS = int(os.getenv("ZEROXZERO_COOLDOWN_SECONDS", str(6 * 60 * 60)))
ZEROXZERO_DISABLED_UNTIL = 0.0

raw_proxy = os.getenv("ZEROXZERO_PROXY") or os.getenv("PROXY_URL")
PROXY_URL = None
if raw_proxy:
    clean_addr = raw_proxy.split("://")[-1]
    PROXY_URL = f"http://{clean_addr}"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
]


def _read_upload_file(file_source: str) -> tuple[str, bytes]:
    path = Path(file_source)
    return path.name, path.read_bytes()


def _valid_link(text: str) -> str | None:
    link = text.strip()
    if link.startswith("https://0x0.st/") or link.startswith("http://0x0.st/"):
        return link
    return None


def is_0x0_available() -> bool:
    return ZEROXZERO_ENABLED and time.time() >= ZEROXZERO_DISABLED_UNTIL


def _mark_0x0_disabled(reason: str) -> None:
    global ZEROXZERO_DISABLED_UNTIL
    ZEROXZERO_DISABLED_UNTIL = time.time() + ZEROXZERO_COOLDOWN_SECONDS
    logger.warning("0x0 uploads disabled for %.0fs: %s", ZEROXZERO_COOLDOWN_SECONDS, reason[:180])


async def _post_0x0(data=None, files=None, timeout=120.0) -> str | None:
    if not is_0x0_available():
        return None

    strategies = [{"proxy": None, "name": "Direct/System"}]
    if PROXY_URL:
        strategies.append({"proxy": PROXY_URL, "name": "Proxy"})

    headers = {"User-Agent": random.choice(USER_AGENTS)}

    for strategy in strategies:
        try:
            proxy_cfg = strategy["proxy"]
            transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0" if not proxy_cfg else None, retries=2)
            async with httpx.AsyncClient(
                timeout=timeout,
                verify=False,
                proxy=proxy_cfg,
                transport=transport,
                headers=headers,
            ) as client:
                resp = await client.post(ZEROXZERO_ENDPOINT, data=data, files=files)

            if resp.status_code == 200:
                link = _valid_link(resp.text)
                if link:
                    logger.info("0x0 Upload Success (%s): %s", strategy["name"], link)
                    return link
                logger.warning("0x0 returned unexpected response: %s", resp.text[:160])
            elif resp.status_code in {429, 500, 502, 503, 504}:
                if resp.status_code == 503 and "uploads disabled" in resp.text.lower():
                    _mark_0x0_disabled(resp.text)
                    return None
                logger.warning("0x0 %s temporary failure %s. Sleeping 5s.", strategy["name"], resp.status_code)
                await asyncio.sleep(5)
            else:
                logger.warning("0x0 %s failed: %s | %s", strategy["name"], resp.status_code, resp.text[:200])
        except (httpx.ConnectError, httpx.ProxyError, httpx.ReadTimeout, httpx.ConnectTimeout) as exc:
            logger.warning("0x0 %s network error: %r", strategy["name"], exc)
            await asyncio.sleep(1)
        except Exception as exc:
            logger.error("0x0 unexpected error (%s): %r", strategy["name"], exc)
            break

    return None


async def upload_url_to_0x0(file_url: str) -> str | None:
    if not file_url:
        return None
    return await _post_0x0(data={"url": file_url}, timeout=90.0)


async def upload_file_to_0x0(file_path: str) -> str | None:
    if not os.path.exists(file_path):
        logger.error("0x0: file not found %s", file_path)
        return None
    if os.path.getsize(file_path) > ZEROXZERO_MAX_BYTES:
        logger.warning("0x0: file too large for configured limit: %s", file_path)
        return None

    fname, fbytes = await asyncio.to_thread(_read_upload_file, file_path)
    return await upload_bytes_to_0x0(fbytes, fname)


async def upload_bytes_to_0x0(file_bytes: bytes, filename: str) -> str | None:
    if len(file_bytes) > ZEROXZERO_MAX_BYTES:
        logger.warning("0x0: bytes payload too large for configured limit: %s", len(file_bytes))
        return None
    files = {"file": (filename or "file.dat", file_bytes)}
    return await _post_0x0(files=files, timeout=180.0)
