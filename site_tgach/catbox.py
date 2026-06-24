from common.config import HTTP_LOCAL_ADDRESS
import httpx
import logging
import os
import random
import asyncio 
import time
from pathlib import Path

CATBOX_HASH = os.getenv("CATBOX_USER_HASH", None)
CATBOX_HASH_DISABLE_SECONDS = 3600
_CATBOX_HASH_DISABLED_UNTIL = 0.0

# Очистка прокси от схемы (socks5:// и т.д.), чтобы httpx не ругался
raw_proxy = os.getenv("CATBOX_PROXY") or os.getenv("PROXY_URL")
PROXY_URL = None
if raw_proxy:
    clean_addr = raw_proxy.split("://")[-1]
    PROXY_URL = f"http://{clean_addr}"

logger = logging.getLogger("catbox")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
]

async def _send_request(client, url, data, files=None):
    if files:
        return await client.post(url, data=data, files=files)
    return await client.post(url, data=data)


def _catbox_hash_is_enabled() -> bool:
    return bool(CATBOX_HASH) and time.time() >= _CATBOX_HASH_DISABLED_UNTIL


def _build_data(req_type: str, file_source):
    data = {'reqtype': req_type}
    if req_type == 'urlupload':
        data['url'] = file_source
    if _catbox_hash_is_enabled():
        data['userhash'] = CATBOX_HASH
    return data


def _is_invalid_uploader(resp: httpx.Response) -> bool:
    return resp.status_code == 412 and "invalid uploader" in resp.text.lower()


def _disable_bad_catbox_hash():
    global _CATBOX_HASH_DISABLED_UNTIL
    _CATBOX_HASH_DISABLED_UNTIL = time.time() + CATBOX_HASH_DISABLE_SECONDS
    logger.warning("Catbox userhash rejected; using anonymous upload for a while.")


def _read_upload_file(file_source: str) -> tuple[str, bytes]:
    path = Path(file_source)
    return path.name, path.read_bytes()

async def _upload_logic(req_type, file_source, is_file=False):
    """
    Универсальная логика с защитой от спама (Backoff).
    """
    url = "https://catbox.moe/user/api.php"
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    
    strategies = [{"proxy": None, "name": "Direct/System"}]
    if PROXY_URL:
        strategies.append({"proxy": PROXY_URL, "name": "Proxy"})

    request_timeout = 120.0 if is_file else 60.0

    for strategy in strategies:
        try:
            proxy_cfg = strategy["proxy"]
            mode_name = strategy["name"]
            
            bind_addr = HTTP_LOCAL_ADDRESS if not proxy_cfg else None
            transport = httpx.AsyncHTTPTransport(local_address=bind_addr, retries=3)

            async with httpx.AsyncClient(
                timeout=request_timeout, 
                verify=False, 
                proxy=proxy_cfg, 
                transport=transport,
                # trust_env=False оставляем убранным (дефолт True), как в hf_batcher
                headers=headers
            ) as client:
                
                if is_file:
                    # Поддержка загрузки из памяти: (filename, bytes)
                    if isinstance(file_source, tuple):
                        fname, fbytes = file_source
                        files = {'fileToUpload': (fname, fbytes)}
                        data = _build_data(req_type, file_source)
                        if mode_name == "Proxy":
                            logger.info(f"⬆️ Uploading BYTES to Catbox ({mode_name})...")
                        resp = await _send_request(client, url, data, files)
                    else:
                        if not os.path.exists(file_source):
                            logger.error(f"Catbox: File not found {file_source}")
                            return None
                        
                        fname, fbytes = await asyncio.to_thread(_read_upload_file, file_source)
                        files = {'fileToUpload': (fname, fbytes)}
                        data = _build_data(req_type, file_source)
                        if mode_name == "Proxy":
                            logger.info(f"⬆️ Uploading FILE to Catbox ({mode_name})...")
                        resp = await _send_request(client, url, data, files)
                else:
                    files = None
                    data = _build_data(req_type, file_source)
                    resp = await _send_request(client, url, data)

                if data.get('userhash') and _is_invalid_uploader(resp):
                    _disable_bad_catbox_hash()
                    anonymous_data = dict(data)
                    anonymous_data.pop('userhash', None)
                    resp = await _send_request(client, url, anonymous_data, files)

                if resp.status_code == 200:
                    link = resp.text.strip()
                    if link.startswith("http"):
                        logger.info(f"✅ Catbox Upload Success ({mode_name}): {link}")
                        return link
                    else:
                        logger.warning(f"⚠️ Catbox returned weird response: {link[:100]}")
                
                elif resp.status_code in [429, 500, 502, 503]:
                    logger.warning(f"⚠️ Catbox {mode_name} Overload ({resp.status_code}). Sleeping 5s...")
                    await asyncio.sleep(5)
                else:
                    logger.warning(f"❌ Catbox ({mode_name}) Failed: {resp.status_code} | Resp: {resp.text[:200]}")

        except (httpx.ConnectError, httpx.ProxyError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
            logger.warning(f"⚠️ Catbox {strategy['name']} Network Error: {repr(e)}")
            await asyncio.sleep(1)
            continue
        except Exception as e:
            logger.error(f"⛔ Catbox Unexpected Error ({strategy['name']}): {repr(e)}")
            break 
            
    return None

async def upload_url_to_catbox(file_url: str) -> str | None:
    """Для мелких файлов: отдает ссылку Кетбоксу."""
    return await _upload_logic('urlupload', file_url, is_file=False)

async def upload_file_to_catbox(file_path: str) -> str | None:
    """Для тяжелых файлов с диска."""
    return await _upload_logic('fileupload', file_path, is_file=True)

async def upload_bytes_to_catbox(file_bytes: bytes, filename: str) -> str | None:
    """Для тяжелых файлов из памяти."""
    return await _upload_logic('fileupload', (filename, file_bytes), is_file=True)  
