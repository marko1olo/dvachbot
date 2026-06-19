import asyncio
import httpx
import re
import random
import os
import json
import time
import logging
import traceback
from datetime import datetime
from io import BytesIO
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning

# Импорты проекта
from warhammer_mode import warhammer_transform
from site_tgach.image_processing import apply_grimdark_filter_async, process_and_upload_image
from common.bot_pool import global_bot_pool
from common.async_file_io import read_json_file_async
from common.secret_redaction import install_logging_redaction
# Добавлены функции очередей из старой версии
import uuid
from common.database import (
    get_db_connection, 
    register_file_owner, 
    add_to_mirror_queue, 
    add_to_hf_queue,
    create_post,
    create_thread_entry,
    update_post_content,
    get_post_for_broadcast,
    update_thread_last_updated,
    process_backlinks
)
from common.db_pool import db_lock
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
install_logging_redaction()
logger = logging.getLogger("importer")

PROXY_URL = "http://127.0.0.1:10808"
RE_LINK_REF = re.compile(r'(?:>>|&gt;&gt;)(\d+)')

class MemoryUploadFile:
    """
    Класс-обертка для BytesIO, имитирующий поведение UploadFile из FastAPI.
    """
    __slots__ = ('file', 'filename', 'content_type', 'headers', 'size')
    def __init__(self, file: BytesIO, filename: str, content_type: str):
        self.file = file
        self.filename = filename
        self.content_type = content_type
        self.headers = {"content-type": content_type}
        self.size = file.getbuffer().nbytes
    async def read(self, size: int = -1) -> bytes:
        return self.file.read(size)
    async def seek(self, offset: int) -> int:
        return self.file.seek(offset)
    async def close(self) -> None:
        pass

class ThreadImporter:
    MEDIA_CONCURRENCY_LIMIT = 5

    def __init__(self, bot, file_storage_channel_id: int):
        self.bot = bot
        self.channel_id = file_storage_channel_id
        self.client: Optional[httpx.AsyncClient] = None
        self._cpu_executor = ThreadPoolExecutor(max_workers=4)
        self.created_post_ids: List[int] = []

    async def _cleanup(self) -> None:
        """
        Механизм отката транзакции. Если во время вставки произошла ошибка,
        удаляет все уже созданные посты.
        """
        if not self.created_post_ids: return
        logger.warning(f"⚠️ ROLLBACK: Удаление {len(self.created_post_ids)} созданных постов...")
        try:
            async with db_lock, get_db_connection() as conn:
                chunk_size = 900
                for i in range(0, len(self.created_post_ids), chunk_size):
                    chunk = self.created_post_ids[i:i + chunk_size]
                    if not chunk: continue
                    placeholders = ','.join(['?'] * len(chunk))
                    await conn.execute(f"DELETE FROM Posts WHERE post_num IN ({placeholders})", chunk)
                    str_chunk = [str(x) for x in chunk] 
                    await conn.execute(f"DELETE FROM Threads WHERE thread_id IN ({placeholders})", str_chunk)
                await conn.commit()
            logger.info("✅ Rollback выполнен успешно.")
        except Exception as e:
            logger.error(f"❌ CRITICAL ROLLBACK FAIL: {e}", exc_info=True)

    def _normalize_html_sync(self, raw_html: str) -> str:
        if not raw_html: return ""
        
        import html as html_lib
        raw_html = html_lib.unescape(raw_html)

        replacements = {
            r'двач': 'тгач',
            r'харкач': 'тгач',
            r'сосач': 'тгач',
            r'двачер': 'тгачер',
            r'двощ': 'тгач',
            r'абу': 'админ',
            r'mailru': 'tganon',
            r'2ch': 'tgach',
            r'2ch.su': 'tgach.site',
            r'2ch.org': 'tgach.site',
            r'2chan': 'tgach',
            r'4chan': 'tgach',
            r'4chan.org': 'tgach.site'
        }
        for pattern, replacement in replacements.items():
            raw_html = re.sub(pattern, replacement, raw_html, flags=re.IGNORECASE)
        
        import warnings
        warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)
        
        try:
            soup = BeautifulSoup(raw_html, "lxml")
        except Exception:
            soup = BeautifulSoup(raw_html, "html.parser")
            
        for tag in soup.find_all(['script', 'style', 'iframe', 'object', 'embed', 'applet', 'form', 'button', 'meta', 'link', 'wbr', 'img']):
            tag.decompose()
        for br in soup.find_all("br"):
            br.replace_with("\n")
        for block in soup.find_all(["p", "div"]):
            block.insert_after("\n")
            block.unwrap()
        for span in soup.find_all("span", class_="spoiler"):
            content = span.get_text()
            span.replace_with(f"||{content}||")
        for a in soup.find_all('a'):
            href = a.get_text()
            a.replace_with(href)
            
        clean_text = soup.get_text()
        clean_text = re.sub(r'\s*\(OP\)', '', clean_text)
        clean_text = re.sub(r' +', ' ', clean_text)
        clean_text = re.sub(r'\n\s*\n', '\n\n', clean_text)
        return clean_text.strip()

    async def normalize_html(self, raw_html: str) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._cpu_executor, self._normalize_html_sync, raw_html)

    async def _safe_request(self, url: str, retries: int = 3) -> Optional[httpx.Response]:
        url = url.strip()
        is_4chan_media = "i.4cdn.org" in url
        for i in range(retries):
            try:
                if is_4chan_media:
                    # Для 4chan создаем отдельный клиент, чтобы обойти возможные блокировки по заголовкам
                    ua = self.client.headers.get("user-agent", "")
                    clean_headers = {"User-Agent": ua}
                    async with httpx.AsyncClient(
                        verify=False, 
                        http2=False, 
                        timeout=180.0,
                        proxy=PROXY_URL,
                        transport=httpx.AsyncHTTPTransport(local_address="0.0.0.0", retries=3)
                    ) as clean_client:
                        resp = await clean_client.get(url, headers=clean_headers)
                else:
                    resp = await self.client.get(url, timeout=180.0)
                
                if resp.status_code == 200:
                    return resp
                if resp.status_code == 404:
                    logger.warning(f"⚠️ 404 Not Found: {url}")
                    return None
                if resp.status_code in [403, 503, 429]:
                    logger.warning(f"⚠️ Server returned {resp.status_code}. Retrying...")
                    await asyncio.sleep(2 * (i + 1))
                    continue
                resp.raise_for_status()
                return resp
            except httpx.TimeoutException:
                logger.error(f"⏰ TIMEOUT reading {url} (Attempt {i+1})")
                if i == retries - 1:
                    logger.error("❌ Giving up on timeout.")
                await asyncio.sleep(1)
            except Exception as e:
                err_name = type(e).__name__
                logger.error(f"❌ ERROR ({err_name}) downloading {url}: {e}")
                if i == retries - 1:
                    logger.error(f"❌ Failed final request to {url}")
                await asyncio.sleep(1.0)
        return None

    async def fetch_json(self, url: str) -> Any:
        target_url = url.strip().split('#')[0]
        # Логика преобразования URL (4chan, dobrochan, 2chan)
        if "4chan.org" in target_url or "4channel.org" in target_url:
            parts = target_url.split('/')
            try:
                if 'thread' in parts:
                    idx = parts.index('thread')
                    board = parts[idx - 1]
                    thread_id = parts[idx + 1].split('.')[0]
                    target_url = f"https://a.4cdn.org/{board}/thread/{thread_id}.json"
            except ValueError:
                pass 
        if "dobrochan" in target_url:
            if target_url.endswith('.xhtml') or target_url.endswith('.html'):
                target_url = target_url.replace('.xhtml', '.json').replace('.html', '.json')
        elif "2chan.net" in target_url:
            if target_url.endswith('.htm'):
                target_url = target_url.replace('.htm', '.json')
            elif not target_url.endswith('.json'):
                target_url += '.json'
        elif target_url.endswith('.html'):
            target_url = target_url.replace('.html', '.json')

        logger.info(f"🌐 Fetching JSON: {target_url}")
        try:
            MAX_JSON_SIZE = 10 * 1024 * 1024 
            async with self.client.stream("GET", target_url, follow_redirects=True) as response:
                if response.status_code != 200:
                    raise Exception(f"HTTP {response.status_code}")
                data_accumulated = b""
                async for chunk in response.aiter_bytes():
                    data_accumulated += chunk
                    if len(data_accumulated) > MAX_JSON_SIZE:
                        raise Exception("JSON too large (Limit 10MB)")
                return json.loads(data_accumulated)
        except Exception as e:
            logger.error(f"Fetch error: {e}")
            raise e
        except json.JSONDecodeError:
            raise Exception("Server returned non-JSON response")

    def extract_posts_data(self, json_data: Any) -> List[Dict]:
        if isinstance(json_data, dict):
            if 'posts' in json_data:
                return json_data['posts']
            if 'threads' in json_data and isinstance(json_data['threads'], list):
                return json_data['threads'][0].get('posts', [])
            for v in json_data.values():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    if any(k in v[0] for k in ('comment', 'no', 'num', 'com')):
                        return v
        elif isinstance(json_data, list):
            return json_data
        raise ValueError("Unknown JSON structure: could not find posts list")

    async def _process_single_post_media(self, post: Dict, base_url: str, domain_root: str, semaphore: asyncio.Semaphore, stream: str = 'ru', board_id: str = 'b') -> List[Dict]:
        """
        Универсальный загрузчик файлов.
        """
        uploaded_files = []
        files_to_download = [] 
        
        # Сбор ссылок на файлы из JSON
        if post.get('files'):
            for f in post['files']:
                path = f.get('path') or f.get('src') or f.get('url')
                name = f.get('name') or f.get('filename') or f.get('displayname') or f.get('fullname')
                if not path and f.get('thumbnail'):
                    path = f['thumbnail']
                if path:
                    if not name: name = str(path).split('/')[-1]
                    files_to_download.append({'path': str(path), 'name': str(name)})
        
        tim = post.get('tim') or post.get('renamed_filename')
        ext = post.get('ext')
        if tim and ext:
            filename = str(tim) + str(ext)
            display_name = (post.get('filename') or str(tim)) + str(ext)
            if not any(f['name'] == display_name for f in files_to_download):
                files_to_download.append({'path': filename, 'name': display_name})
        
        if post.get('extra_files'):
            for ef in post['extra_files']:
                if ef.get('tim') and ef.get('ext'):
                    filename = str(ef['tim']) + str(ef['ext'])
                    display_name = (ef.get('filename') or str(ef['tim'])) + str(ef['ext'])
                    files_to_download.append({'path': filename, 'name': display_name})

        target_files = files_to_download[:4]
        if not target_files: return []

        downloaded_versions = []

        async with semaphore:
            for f in target_files:
                raw_path = f['path'].strip()
                if not raw_path: continue
                urls_to_try = []
                if raw_path.startswith('http'):
                    urls_to_try.append(raw_path)
                elif raw_path.startswith('//'):
                    urls_to_try.append(f"https:{raw_path}")
                elif raw_path.startswith('/'):
                    urls_to_try.append(f"{domain_root}{raw_path}")
                else:
                    if "ejchan" in domain_root or "ejchan" in base_url:
                        if "/res/" in base_url:
                            src_base = base_url.replace("/res/", "/src/")
                            urls_to_try.append(f"{src_base}{raw_path}")
                        elif "/src/" not in base_url:
                            urls_to_try.append(f"{base_url}src/{raw_path}")
                        urls_to_try.append(f"{base_url}{raw_path}")
                    elif "4cdn" in base_url:
                        urls_to_try.append(f"{base_url}{raw_path}")
                    elif "2chan.net" in domain_root:
                        urls_to_try.append(f"{base_url}{raw_path}")
                        if "/res/" in base_url:
                            root_board = base_url.replace("/res/", "/")
                            urls_to_try.append(f"{root_board}src/{raw_path}")
                    else:
                        urls_to_try.append(f"{base_url}{raw_path}")
                        if '/' not in raw_path:
                            urls_to_try.append(f"{base_url}src/{raw_path}")

                downloaded_buffer = None
                content_type = None
                
                for media_url in urls_to_try:
                    try:
                        resp = await self._safe_request(media_url, retries=2)
                        if resp and resp.status_code == 200:
                            ct = resp.headers.get("content-type", "")
                            if "text/html" in ct:
                                logger.warning(f"⚠️ Got HTML instead of image from {media_url}")
                                continue
                            downloaded_buffer = BytesIO(resp.content)
                            content_type = ct or "application/octet-stream"
                            break
                        
                        # Warhammer Grimdark Filter (если нужно)
                        if board_id == 'wh40k' and content_type and content_type.startswith('image/'):
                                raw_bytes = downloaded_buffer.getvalue()
                                processed_bytes = await apply_grimdark_filter_async(raw_bytes)
                                downloaded_buffer = BytesIO(processed_bytes)
                    except Exception:
                        continue
                
                if not downloaded_buffer:
                    continue
                downloaded_versions.append({
                    "buffer": downloaded_buffer,
                    "name": f['name'],
                    "content_type": content_type,
                    "size": downloaded_buffer.getbuffer().nbytes
                })
        if not downloaded_versions:
            return []
        for file_data in downloaded_versions:
            try:
                fake_file = MemoryUploadFile(file_data["buffer"], file_data["name"], file_data["content_type"])
                
                if global_bot_pool:
                    uploader_bot_id, uploader_bot = global_bot_pool.get_next_bot(stream)
                else:
                    uploader_bot = self.bot
                    uploader_bot_id = getattr(self.bot, 'id', 0)
                res = await process_and_upload_image(fake_file, 50*1024*1024, uploader_bot, self.channel_id)
                
                if res:
                    fname = res.get('filename') or file_data["name"]
                    res['filename'] = fname
                    
                    oid = res.get('original_file_id')
                    if oid:
                        if str(oid).startswith(('http://', 'https://')):
                            res['original_url'] = oid
                        else:
                            res['original_url'] = f"/files/{str(oid).strip('/')}"
                    else:
                        res['original_url'] = f"/files/{fname}"

                    tid = res.get('thumbnail_file_id')
                    if tid:
                        if not str(tid).startswith(('http://', 'https://')):
                            res['thumbnail_url'] = f"/files/{str(tid).strip('/')}"
                        else:
                            res['thumbnail_url'] = tid

                    res['_bot_id'] = uploader_bot_id
                    uploaded_files.append(res)
                    
                    if uploader_bot_id:
                        if oid and not str(oid).startswith('http'):
                            await register_file_owner(oid, uploader_bot_id)
                        if tid and not str(tid).startswith('http'):
                            await register_file_owner(tid, uploader_bot_id)
            except Exception as e:
                logger.error(f"⚠️ Upload error for file {file_data['name']}: {e}")
                continue
            
        return uploaded_files

    async def _fix_content_links_and_find_reply(self, text: str, id_map: Dict[str, int]) -> Tuple[str, Optional[int]]:
        if not text:
            return text, None
        reply_to_id = None
        def replace_ref(match):
            nonlocal reply_to_id
            old_ref = match.group(1)
            if old_ref in id_map:
                new_id = id_map[old_ref]
                if reply_to_id is None:
                    reply_to_id = new_id
                return f">>{new_id}"
            return "" 
        new_text = RE_LINK_REF.sub(replace_ref, text)
        return new_text, reply_to_id

    async def process_thread(self, source_url: str, target_board: str, stream: str = 'ru', sim_settings: dict = None):
        start_time = time.time()
        use_sim = sim_settings and sim_settings.get('enabled', False)
        task_id = str(uuid.uuid4()) if use_sim else None
        logger.info(f"🚀 START IMPORT: {source_url} -> /{target_board}/ [{stream}] Sim: {use_sim}")
        
        parsed_url = urlparse(source_url)
        current_referer = f"{parsed_url.scheme}://{parsed_url.netloc}/"
        current_origin = f"{parsed_url.scheme}://{parsed_url.netloc}"
        
        # Cookie logic
        cookie_filename = 'cookies.json'
        if "4chan.org" in source_url or "4channel.org" in source_url or "4cdn.org" in source_url:
            cookie_filename = 'cookies_4chan.json'
            logger.info("🍪 Detected 4chan. Using cookies_4chan.json")
        cookies = {}
        try:
            base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            cookie_path = os.path.join(base_path, cookie_filename)
            if not os.path.exists(cookie_path):
                 cookie_path = cookie_filename
            if os.path.exists(cookie_path):
                cookies = await read_json_file_async(cookie_path)
                logger.info(f"🍪 Loaded cookies from {cookie_filename}: {list(cookies.keys())}")
            else:
                logger.warning(f"⚠️ Cookie file {cookie_filename} not found.")
        except Exception as e:
            logger.warning(f"⚠️ Cookie load error: {e}")
        
        custom_ua = cookies.pop('user_agent', None) 
        headers = {
            "User-Agent": custom_ua or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": current_referer,
            "Origin": current_origin,
            "Connection": "keep-alive"
        }

        # Configured Transport from New Version
        transport = httpx.AsyncHTTPTransport(
            local_address="0.0.0.0", # Принудительный IPv4 (Fix для OpenVPN)
            retries=3,
            verify=False,
            http2=False              # Строго HTTP/1.1
        )

        async with httpx.AsyncClient(
            transport=transport,
            follow_redirects=True, 
            headers=headers, 
            cookies=cookies,
            trust_env=True,
            proxy=PROXY_URL,
            timeout=180.0
        ) as client:
            self.client = client
            self.created_post_ids.clear()
            
            try:
                # === Phase 1: Fetching JSON ===
                logger.info("⏳ Phase 1: Fetching & Parsing JSON...")
                try:
                    data = await self.fetch_json(source_url)
                    posts = self.extract_posts_data(data)
                    logger.info(f"✅ Phase 1 SUCCESS: Found {len(posts)} posts.")
                except Exception as e:
                    logger.error(f"❌ Phase 1 FAIL: Failed to fetch/parse thread JSON: {e}", exc_info=True)
                    return

                total_posts = len(posts)
                if total_posts == 0:
                    logger.warning("⚠️ Empty thread, skipping.")
                    return

                # Persona Setup
                unique_personas_count = max(3, int(total_posts / 4.5))
                personas = [int(random.randint(-9999999, -1000000)) for _ in range(unique_personas_count)]
                op_persona_id = personas[0]

                # URL Logic
                base_url = source_url
                is_4chan = "4chan" in source_url or "4channel" in source_url or "4cdn" in source_url
                parsed_source = urlparse(source_url)
                domain_root = f"{parsed_source.scheme}://{parsed_source.netloc}"
                if is_4chan:
                    parts = source_url.split('/')
                    board_name = "b" 
                    for i, p in enumerate(parts):
                        if 'boards.4chan' in p or 'boards.4channel' in p:
                            if i+1 < len(parts): board_name = parts[i+1]
                            break
                    base_url = f"https://i.4cdn.org/{board_name}/"
                else:
                    base_url = "/".join(source_url.split('/')[:-1]) + "/"

                logger.info(f"📷 Media Base URL: {base_url}")
                
                # === Phase 2: Processing Posts ===
                prepared_posts = []
                semaphore = asyncio.Semaphore(self.MEDIA_CONCURRENCY_LIMIT)
                logger.info("⏳ Phase 2: Downloading media & normalizing HTML...")
                
                next_log_threshold = 0 
                for i, p in enumerate(posts):
                    # Logging Progress
                    current_pct = (i + 1) / total_posts * 100
                    if current_pct >= next_log_threshold or i == total_posts - 1:
                        logger.info(f"   ...Processed {i+1}/{total_posts} posts ({int(current_pct)}%)")
                        next_log_threshold += 10
                    
                    try:
                        old_id = str(p.get('num') or p.get('no') or p.get('id') or i)
                        raw_text = p.get('comment') or p.get('com') or p.get('body') or ""
                        raw_text = raw_text.replace('<wbr>', '')
                        clean_text = await self.normalize_html(raw_text)
                        
                        if target_board == 'wh40k':
                            _, w_content = warhammer_transform(clean_text, allow_image=False)
                            clean_text = w_content
                            
                        is_op = (i == 0)
                        author_id = op_persona_id if is_op else random.choice(personas)
                        if not use_sim:
                            offset_seconds = (total_posts - i) * 60 
                            post_timestamp = time.time() - offset_seconds
                        else:
                            post_timestamp = 0
                        
                        files_data = await self._process_single_post_media(p, base_url, domain_root, semaphore, stream, board_id=target_board)
                        
                        prepared_posts.append({
                            "old_id": old_id,
                            "text": clean_text,
                            "files": files_data,
                            "timestamp": post_timestamp,
                            "author_id": author_id,
                            "is_op": is_op,
                            "raw_text": p.get('comment') or p.get('com') or ""
                        })
                    except Exception as post_error:
                        logger.error(f"⚠️ Error processing post {i} (skipped): {post_error}")
                        continue
                
                if not prepared_posts:
                    return

                if use_sim:
                    await self._queue_posts_for_simulation(prepared_posts, target_board, stream, task_id, sim_settings)
                else:
                    await self._instant_import(prepared_posts, target_board, stream)

            except Exception as e:
                logger.error(f"❌ Global Import Error: {e}", exc_info=True)
            finally:
                self.client = None
                self.created_post_ids.clear()

    async def _queue_posts_for_simulation(self, posts: List[Dict], board_id: str, stream: str, task_id: str, settings: dict):
        start_delay = settings.get('start_delay_mins', 0) * 60
        min_int = settings.get('interval_min', 20)
        max_int = settings.get('interval_max', 120)
        
        current_publish_time = time.time() + start_delay
        queue_items = []
        op_title = ""
        
        for i, p in enumerate(posts):
            if i > 0:
                current_publish_time += random.randint(min_int, max_int)
            
            reply_to_old_id = None
            refs = re.findall(r'(?:>>|&gt;&gt;)(\d+)', p['raw_text'])
            if refs:
                reply_to_old_id = refs[0]
            
            content_json = json.dumps({
                "text": p["text"], 
                "files": p["files"], 
                "type": "files" if p["files"] else "text"
            })
            
            if p['is_op']:
                op_title = p["text"][:100] if p["text"] else "Imported Thread"

            queue_items.append((
                task_id, board_id, p['old_id'], reply_to_old_id,
                current_publish_time, content_json, p['author_id'],
                stream, 1 if p['is_op'] else 0,
                op_title if p['is_op'] else None, time.time()
            ))
            
        async with db_lock, get_db_connection() as conn:
            await conn.executemany("""
                INSERT INTO ImportQueue 
                (task_id, board_id, original_post_num, reply_to_original, publish_at, content, author_id, stream, is_op, thread_title, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, queue_items)
            await conn.commit()

    async def _instant_import(self, prepared_posts: List[Dict], target_board: str, stream: str):
        id_map: Dict[str, int] = {} 
        new_thread_id = None
        all_files_for_queue = []
        for p_data in prepared_posts:
            for f in p_data["files"]:
                if f.get("original_file_id"):
                    all_files_for_queue.append(f["original_file_id"])

        async with db_lock, get_db_connection() as conn:
            try:
                await conn.execute("BEGIN")
                op_data = prepared_posts[0]
                op_content = json.dumps({
                    "text": op_data["text"], 
                    "files": op_data["files"], 
                    "type": "files" if op_data["files"] else "text"
                })
                cur = await conn.execute(
                    """INSERT INTO posts 
                       (board_id, thread_id, content, timestamp, author_id, reply_to_post_num, stream) 
                       VALUES (?, NULL, ?, ?, ?, NULL, ?) RETURNING post_num""",
                    (target_board, op_content, op_data["timestamp"], op_data["author_id"], stream)
                )
                new_op_id = (await cur.fetchone())[0]
                self.created_post_ids.append(new_op_id)
                new_thread_id = new_op_id
                id_map[op_data["old_id"]] = new_op_id

                await conn.execute("UPDATE posts SET thread_id = ? WHERE post_num = ?", (new_thread_id, new_op_id))
                title = op_data["text"][:100] if op_data["text"] else "Imported Thread"
                await conn.execute(
                    """INSERT INTO Threads 
                       (thread_id, thread_num, board_id, op_id, title, created_at, last_updated_at, is_archived, stream) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)""",
                    (new_thread_id, new_thread_id, target_board, op_data["author_id"], title, op_data["timestamp"], time.time(), stream)
                )
                await conn.commit()
                
                chunk_size = 20
                replies_data = prepared_posts[1:]
                for i in range(0, len(replies_data), chunk_size):
                    await conn.execute("BEGIN")
                    chunk = replies_data[i : i + chunk_size]
                    for p_data in chunk:
                        content = json.dumps({
                            "text": p_data["text"], 
                            "files": p_data["files"], 
                            "type": "files" if p_data["files"] else "text"
                        })
                        cur = await conn.execute(
                            """INSERT INTO posts 
                               (board_id, thread_id, content, timestamp, author_id, reply_to_post_num, stream) 
                               VALUES (?, ?, ?, ?, ?, NULL, ?) RETURNING post_num""",
                            (target_board, new_thread_id, content, p_data["timestamp"], p_data["author_id"], stream)
                        )
                        new_id = (await cur.fetchone())[0]
                        self.created_post_ids.append(new_id)
                        id_map[p_data["old_id"]] = new_id
                    await conn.commit()
                    await asyncio.sleep(0.05)
                
                await conn.execute("BEGIN")
                unique_authors = set(p["author_id"] for p in prepared_posts)
                for uid in unique_authors:
                    await conn.execute("INSERT OR IGNORE INTO Users (user_id, board_id, stream) VALUES (?, ?, ?)", (uid, target_board, stream))
                
                from common.config import STORAGE_CHANNELS
                current_channel = STORAGE_CHANNELS.get(stream, STORAGE_CHANNELS['ru'])
                for p_data in prepared_posts:
                    p_num = id_map.get(p_data["old_id"])
                    if not p_num: continue
                    for f in p_data["files"]:
                        if f.get('channel_message_id'):
                            await conn.execute("INSERT OR IGNORE INTO ChannelCopies (post_num, channel_id, message_id) VALUES (?, ?, ?)", 
                                             (p_num, current_channel, f['channel_message_id']))
                await conn.commit()
                
                for i in range(0, len(prepared_posts), chunk_size):
                    await conn.execute("BEGIN")
                    chunk = prepared_posts[i : i + chunk_size]
                    for p_data in chunk:
                        new_id = id_map[p_data["old_id"]]
                        original_text = p_data["text"]
                        if not original_text: continue
                        fixed_text, reply_to_id = await self._fix_content_links_and_find_reply(original_text, id_map)
                        if fixed_text != original_text or reply_to_id is not None:
                            new_content_obj = {"text": fixed_text, "files": p_data["files"], "type": "files" if p_data["files"] else "text"}
                            await conn.execute("UPDATE posts SET content = ?, reply_to_post_num = ? WHERE post_num = ?", 
                                             (json.dumps(new_content_obj), reply_to_id, new_id))
                        
                            backlink_pairs = []
                            if reply_to_id:
                                backlink_pairs.append((reply_to_id, new_id))
                            
                            refs = set(re.findall(r'>>(\d+)', fixed_text))
                            for ref in refs:
                                try:
                                    target_id = int(ref)
                                    if target_id != new_id:
                                        backlink_pairs.append((target_id, new_id))
                                except: pass
                            
                            if backlink_pairs:
                                await conn.executemany(
                                    "INSERT OR IGNORE INTO Backlinks (target_post_num, source_post_num) VALUES (?, ?)",
                                    backlink_pairs
                                )
                            
                    await conn.commit()

                if all_files_for_queue:
                    for fid in all_files_for_queue:
                        await add_to_mirror_queue(fid, 'catbox')
                        await add_to_hf_queue(fid)

            except Exception as e:
                if conn.in_transaction: await conn.rollback()
                await self._cleanup()
                raise e

async def process_import_queue(app_state_broadcast_queue):
    while True:
        try:
            now = time.time()
            async with get_db_connection() as conn:
                async with conn.execute("""
                    SELECT id, task_id, board_id, original_post_num, reply_to_original, 
                           content, author_id, stream, is_op, thread_title 
                    FROM ImportQueue 
                    WHERE publish_at <= ? 
                    ORDER BY publish_at ASC, original_post_num ASC 
                    LIMIT 10
                """, (now,)) as cursor:
                    rows = await cursor.fetchall()
                    
                if not rows:
                    await asyncio.sleep(5)
                    continue
                
                for row in rows:
                    q_id, task_id, board_id, orig_num, reply_to_orig, content_str, author_id, stream, is_op, title = row
                    try:
                        content = json.loads(content_str)
                        text = content.get('text', '')
                        
                        refs = re.findall(r'(?:>>|&gt;&gt;)(\d+)', text)
                        replacements = {}
                        real_reply_to = None
                        
                        if refs:
                            placeholders = ','.join(['?'] * len(refs))
                            q_map = f"SELECT original_post_num, real_post_num FROM ImportRefMap WHERE task_id = ? AND original_post_num IN ({placeholders})"
                            async with conn.execute(q_map, [task_id] + refs) as map_cur:
                                async for m_row in map_cur:
                                    replacements[m_row[0]] = m_row[1]
                        
                        for old_ref, new_ref in replacements.items():
                            text = text.replace(f">>{old_ref}", f">>{new_ref}")
                            text = text.replace(f"&gt;&gt;{old_ref}", f"&gt;&gt;{new_ref}")
                        content['text'] = text
                        
                        if reply_to_orig and reply_to_orig in replacements:
                            real_reply_to = replacements[reply_to_orig]
                        
                        final_thread_id_db = None
                        if not is_op:
                            async with conn.execute("SELECT real_post_num FROM ImportRefMap WHERE task_id = ? ORDER BY rowid ASC LIMIT 1", (task_id,)) as op_cur:
                                op_row = await op_cur.fetchone()
                                if op_row: final_thread_id_db = str(op_row[0])
                        
                        post_mode = 'new_thread' if is_op else 'reply'
                        new_post_num = await create_post(
                            author_id=author_id,
                            board_id=board_id,
                            content=content,
                            timestamp=time.time(),
                            reply_to=real_reply_to,
                            is_from_site=True,
                            post_mode=post_mode,
                            stream=stream,
                            thread_id_from_bot=final_thread_id_db
                        )
                        
                        if new_post_num:
                            if is_op:
                                await create_thread_entry(new_post_num, board_id, author_id, title or "Imported", time.time(), stream=stream)
                            elif final_thread_id_db:
                                await update_thread_last_updated(int(final_thread_id_db), time.time())
                            await process_backlinks(new_post_num, content['text'], real_reply_to)

                            async with db_lock:
                                await conn.execute("INSERT INTO ImportRefMap (task_id, original_post_num, real_post_num) VALUES (?, ?, ?)", (task_id, orig_num, new_post_num))
                                await conn.execute("DELETE FROM ImportQueue WHERE id = ?", (q_id,))
                                await conn.commit()
                            
                            if app_state_broadcast_queue:
                                bp = await get_post_for_broadcast(new_post_num)
                                if bp: await app_state_broadcast_queue.put(bp)
                                
                            logger.info(f"🎭 [Sim] Published #{new_post_num} (was {orig_num}) on /{board_id}/")
                            
                            await asyncio.sleep(random.uniform(0.5, 2.5)) 
                            
                        else:
                            logger.error(f"❌ [Sim] Failed to create post for queue item {q_id}")
                            async with db_lock:
                                await conn.execute("DELETE FROM ImportQueue WHERE id = ?", (q_id,))
                                await conn.commit()
                        
                    except Exception as e:
                        try:
                            async with db_lock:
                                await conn.execute("DELETE FROM ImportQueue WHERE id = ?", (q_id,))
                                await conn.commit()
                        except: pass

        except Exception:
            await asyncio.sleep(10)
