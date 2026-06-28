import asyncio
from common.http_utils import api_retry
from common.task_manager import spawn_task
"""
tagging_worker.py
This module contains the implementation of a tagging worker for processing images and videos 
using a neural network for moderation. It includes functions for image processing, 
hash generation, and interaction with a database to manage file metadata.
Key Features:
- Image processing functions to compute SHA256, perceptual hash (pHash), and BlurHash.
- Asynchronous functions to interact with a neural network for tagging images.
- Database operations to retrieve and update file metadata.
- Handling of Telegram bot interactions for downloading files.
Constants:
- logger: Logger instance for logging messages.
- PROXY_URL: URL for proxy settings.
- GROQ_MODEL: Model identifier for the neural network.
- GROQ_TIMEOUT: Timeout setting for network requests.
- BATCH_SIZE: Number of tasks to process in a single batch.
- SUSPICIOUS_KEYWORDS: Set of keywords indicating potentially inappropriate content.
- SAFE_KEYWORDS: Set of keywords indicating safe content.
Functions:
- apply_srgb_to_linear(value): Converts sRGB value to linear color space.
- sign_pow(val, exp): Computes the signed power of a value.
- encode_83(value, length): Encodes a value into a base-83 string.
- encode_dc(value): Encodes the DC component of the BlurHash.
- encode_ac(value, max_val): Encodes the AC components of the BlurHash.
- encode_blurhash_internal(image, components_x, components_y): Encodes an image into a BlurHash string.
- process_image_cpu(image_bytes): Processes an image to compute hashes and resize it for neural network input.
- get_neuro_tags(resized_image_bytes): Asynchronously retrieves tags for an image from the neural network.
- get_tasks(db): Asynchronously retrieves tasks from the database for processing.
- tagging_loop(): Main asynchronous loop for processing tagging tasks.
"""
import logging
import base64
import time
import httpx
import hashlib
import math
import io
import imagehash
from PIL import Image
from openai import AsyncOpenAI

# Импорты проекта
from common.db_pool import get_pool, db_lock
from common.bot_pool import global_bot_pool
from common.token_pool import groq_pool
from aiogram.exceptions import TelegramBadRequest

# Импорт логики модерации
from site_tgach.neuro_moderator import TAGGING_PROMPT, run_deep_check

# === НАСТРОЙКИ ===
logger = logging.getLogger("tagger")
PROXY_URL = "http://127.0.0.1:10808"
GROQ_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
GROQ_TIMEOUT = 40.0
BATCH_SIZE = 1  # СТРОГО ПО ОДНОМУ, чтобы не насиловать ключи

GROQ_COOLDOWN_UNTIL = 0
TEMP_FAILED_FILES = {}

SUSPICIOUS_KEYWORDS = {'child', 'kid', 'toddler', 'infant', 'baby', 'teen', 'underage', 'young girl', 'little girl'}
SAFE_KEYWORDS = {'anime', 'illustration', 'sketch', 'digital art', 'painting', '3d_render', 'cartoon', 'manga'}

# ==========================================
# ФУНКЦИИ BLURHASH
# ==========================================
def apply_srgb_to_linear(value):
    v = value / 255.0
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

def sign_pow(val, exp):
    return math.copysign(abs(val) ** exp, val)

def encode_83(value, length):
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz#$%*+,-.:;=?@[]^_{|}~"
    return "".join(chars[(value // (83 ** (length - i))) % 83] for i in range(1, length + 1))

def encode_dc(value):
    rounded = [int(min(255, max(0, v * 255 + 0.5))) for v in value]
    return encode_83(rounded[0] << 16 | rounded[1] << 8 | rounded[2], 4)

def encode_ac(value, max_val):
    quant = [int(max(0, min(18, math.floor(sign_pow(v / max_val, 0.5) * 9 + 9.5)))) for v in value]
    return encode_83(quant[0] * 19 * 19 + quant[1] * 19 + quant[2], 2)

def encode_blurhash_internal(image: Image.Image, components_x: int, components_y: int):
    if image.mode != "RGB":
        image = image.convert("RGB")
    width, height = image.size
    pixels = image.load()
    factors = []
    for y in range(components_y):
        for x in range(components_x):
            normalisation = 1.0 if (x == 0 and y == 0) else 2.0
            r_sum, g_sum, b_sum = 0.0, 0.0, 0.0
            for j in range(height):
                cos_y = math.cos((math.pi * y * j) / height)
                for i in range(width):
                    basis = normalisation * math.cos((math.pi * x * i) / width) * cos_y
                    r, g, b = pixels[i, j]
                    r_sum += apply_srgb_to_linear(r) * basis
                    g_sum += apply_srgb_to_linear(g) * basis
                    b_sum += apply_srgb_to_linear(b) * basis
            scale = 1.0 / (width * height)
            factors.append([r_sum * scale, g_sum * scale, b_sum * scale])
    dc = factors[0]; ac = factors[1:]
    hash_list = []
    size_flag = (components_x - 1) + (components_y - 1) * 9
    hash_list.append(encode_83(size_flag, 1))
    if len(ac) > 0:
        actual_max = max(max(abs(val) for val in band) for band in ac)
        quantised_max = int(max(0, min(82, math.floor(actual_max * 166 - 0.5))))
        max_val = (quantised_max + 1) / 166.0
        hash_list.append(encode_83(quantised_max, 1))
    else:
        max_val = 1.0; hash_list.append(encode_83(0, 1))
    hash_list.append(encode_dc(dc))
    for factor in ac: hash_list.append(encode_ac(factor, max_val))
    return "".join(hash_list)

# ==========================================
# CPU TASKS (HASHER & RESIZER)
# ==========================================
def process_image_cpu(image_bytes):
    """
    1. Считает хеши (SHA, pHash, Blur).
    2. Ресайзит картинку для нейронки (чтобы не ловить 413 Payload Too Large).
    """
    try:
        Image.MAX_IMAGE_PIXELS = 49_000_000 

        if not image_bytes: return None, "Empty bytes"
        
        # 1. SHA256 (всегда)
        sha = hashlib.sha256(image_bytes).hexdigest()

        # 2. Открываем PIL
        try:
            img = Image.open(io.BytesIO(image_bytes))
            img.load()
            if img.mode != 'RGB': img = img.convert('RGB')
        except Image.DecompressionBombError:
            return None, "Decompression Bomb Detected"
        except Exception as e:
            return None, f"PIL Error: {e}"

        # 3. pHash
        phash = str(imagehash.phash(img))
        
        # 4. BlurHash
        try:
            small_blur = img.resize((32, 32), Image.Resampling.BILINEAR)
            b_hash = encode_blurhash_internal(small_blur, 4, 3)
        except Exception as e:
            b_hash = None

        # 5. ПОДГОТОВКА ДЛЯ НЕЙРОНКИ (Ресайз)
        # Groq не любит файлы > 4MB. Ужимаем до 1024px по большей стороне.
        MAX_SIZE = 1024
        if max(img.size) > MAX_SIZE:
            img.thumbnail((MAX_SIZE, MAX_SIZE), Image.Resampling.LANCZOS)
        
        # Сохраняем в JPEG (легче чем PNG)
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        resized_bytes = buffer.getvalue()

        return (sha, phash, b_hash, resized_bytes), None

    except Exception as e:
        return None, f"CPU Error: {e}"

@api_retry
async def _execute_tagging(client, model, messages, max_tokens):
    return await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens
    )

async def get_neuro_tags(resized_image_bytes: bytes) -> str | None:
    global GROQ_COOLDOWN_UNTIL
    
    if time.time() < GROQ_COOLDOWN_UNTIL:
        return None

    if not groq_pool.tokens:
        if time.time() % 60 < 5: logger.warning("⚠️ No Groq tokens available!")
        return None

    try:
        # Картинка уже сжата в process_image_cpu, так что 413 быть не должно
        b64 = base64.b64encode(resized_image_bytes).decode('utf-8')
        url = f"data:image/jpeg;base64,{b64}"
    except Exception as e:
        return None
    
    strategies = [
        {"proxy": PROXY_URL, "name": "Proxy"},
        {"proxy": None, "name": "Direct"}
    ]

    for _ in range(3): 
        token = groq_pool.get_token()
        if not token: break
        
        for strategy in strategies:
            try:
                transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
                async with httpx.AsyncClient(proxy=strategy["proxy"], transport=transport, verify=False, timeout=GROQ_TIMEOUT) as http_client:
                    client = AsyncOpenAI(api_key=token, base_url="https://api.groq.com/openai/v1", http_client=http_client, max_retries=0)
                    resp = await _execute_tagging(
                        client,
                        model=GROQ_MODEL,
                        messages=[{"role": "user", "content": [{"type": "text", "text": TAGGING_PROMPT}, {"type": "image_url", "image_url": {"url": url}}]}],
                        max_tokens=250
                    )
                    content = resp.choices[0].message.content
                    if content:
                        return content.strip().rstrip('.,')
            except Exception as e:
                err_str = str(e).lower()
                if "401" in err_str or "unauthorized" in err_str or "invalid api key" in err_str:
                    logger.error(f"❌ Groq key {token[:12]}... is unauthorized (401). Removing from rotation pool.")
                    groq_pool.remove_token(token)
                    continue
                if "413" in err_str:
                    logger.error("❌ 413 Payload Too Large (Even after resize!). Skipping tags.")
                    return "error_413" # Возвращаем спец-код, чтобы сохранить хеши, но без тегов
                if "429" in err_str or "limit" in err_str:
                    logger.warning(f"Groq Rate Limit. Cooldown 60s.")
                    GROQ_COOLDOWN_UNTIL = time.time() + 60
                    return None
                elif "400" in err_str:
                    return "error_400"
                continue
            
    return None

# ==========================================
# ПОЛУЧЕНИЕ ЗАДАЧ
# ==========================================
async def get_tasks(db) -> list[dict]:
    file_owners = {}
    try:
        async with db.execute("SELECT file_id, bot_id FROM FileOwners") as cursor:
            async for row in cursor:
                file_owners[row[0]] = row[1]
    except Exception: pass
    
    tasks = []
    # 1. Из реестра (только свежие за 24 часа, чтобы не разгребать вечный баклог)
    day_ago = time.time() - 86400
    query_registry = f"""
        SELECT file_id, file_type, thumbnail_id
        FROM FileRegistry
        WHERE file_type IN ('image', 'photo', 'video', 'animation', 'gif', 'video_note') 
        AND (tags IS NULL OR tags = '')
        AND created_at > {day_ago}
        ORDER BY created_at DESC
        LIMIT {BATCH_SIZE * 5}
    """
    try:
        async with db.execute(query_registry) as cursor:
            async for row in cursor:
                tasks.append({
                    'fid': row[0], 
                    'type': row[1], 
                    'thumb_id': row[2], 
                    'bot_id': file_owners.get(row[0])
                })
    except Exception as e:
        logger.error(f"DB Error getting registry tasks: {e}")

    # 2. Поиск пропущенных файлов (Gaps) в последних 250 постах (включая видео)
    if len(tasks) < BATCH_SIZE:
        query_gaps = """
            SELECT DISTINCT 
                json_extract(j.value, '$.original_file_id') as fid, 
                json_extract(j.value, '$.type') as ftype,
                json_extract(j.value, '$.thumbnail_file_id') as thumb_id
            FROM Posts p, json_each(p.content, '$.files') j
            WHERE p.post_num > (SELECT MAX(post_num) - 250 FROM Posts)
              AND ftype IN ('image', 'photo', 'video', 'animation', 'gif', 'video_note')
              AND fid NOT IN (SELECT file_id FROM FileRegistry)
            LIMIT 10
        """
        try:
            async with db.execute(query_gaps) as cursor:
                async for row in cursor:
                    if not any(t['fid'] == row[0] for t in tasks):
                        tasks.append({
                            'fid': row[0], 
                            'type': row[1], 
                            'thumb_id': row[2],
                            'bot_id': file_owners.get(row[0])
                        })
        except Exception: pass

    return tasks[:BATCH_SIZE]

# ==========================================
# ОСНОВНОЙ ЦИКЛ
# ==========================================
async def tagging_loop():
    logger.info("🚀 Tagging Worker Started (Single-Threaded + Resizer)")
    await asyncio.sleep(5)
    
    global TEMP_FAILED_FILES
    if TEMP_FAILED_FILES is None: TEMP_FAILED_FILES = {}
    
    # Считаем бэклог при старте
    try:
        db = await get_pool()
        async with db.execute("SELECT COUNT(*) FROM FileRegistry WHERE file_type IN ('image', 'photo') AND (tags IS NULL OR tags = '' OR phash IS NULL)") as cursor:
            total_backlog = (await cursor.fetchone())[0]
        logger.info(f"📊 GLOBAL STATUS: {total_backlog} files waiting.")
    except: pass

    loop = asyncio.get_running_loop()

    while True:
        try:
            now = time.time()
            if TEMP_FAILED_FILES:
                TEMP_FAILED_FILES = {k: v for k, v in TEMP_FAILED_FILES.items() if v > now}

            db = await get_pool()
            if not db:
                await asyncio.sleep(5); continue

            # Забираем ОДНУ задачу (так как BATCH_SIZE=1)
            all_tasks = await get_tasks(db)
            
            # Фильтруем "временно упавшие"
            valid_task = None
            for t in all_tasks:
                if t['fid'] not in TEMP_FAILED_FILES:
                    valid_task = t
                    break
            
            if not valid_task:
                await asyncio.sleep(2); continue

            file_id = valid_task['fid']
            bot_id = valid_task['bot_id']
            file_type = valid_task['type']
            thumb_id = valid_task.get('thumb_id')

            bot = global_bot_pool.get_bot_by_id(bot_id) if bot_id else global_bot_pool.get_main_bot()
            if not bot:
                TEMP_FAILED_FILES[file_id] = time.time() + 300
                continue

            # Определяем, что качать (для видео качаем превью)
            download_target_id = file_id
            if file_type in ['video', 'animation', 'gif', 'video_note']:
                if not thumb_id:
                    logger.warning(f"⚠️ Video {file_id} has no thumb. Skipping tag.")
                    async with db_lock:
                        await db.execute("UPDATE FileRegistry SET tags='no_thumb' WHERE file_id=?", (file_id,))
                        await db.commit()
                    continue
                download_target_id = thumb_id

            try:
                # 1. СКАЧИВАНИЕ
                try:
                    f_info = await bot.get_file(download_target_id)
                    f_path = getattr(f_info, "file_path", None) if f_info else None
                    if not f_path:
                        logger.error(f"❌ DL fail {download_target_id}: No file_path returned.")
                        TEMP_FAILED_FILES[file_id] = time.time() + 120
                        continue
                    f_obj = await bot.download_file(f_path)
                    img_bytes = f_obj.read() if hasattr(f_obj, 'read') else f_obj
                except TelegramBadRequest:
                    logger.error(f"🗑️ File {download_target_id} deleted. Marking error.")
                    async with db_lock:
                        await db.execute("UPDATE FileRegistry SET tags='error' WHERE file_id=?", (file_id,))
                        await db.commit()
                    continue
                except Exception as e:
                    err_str = str(e).lower()
                    if "logged out" in err_str or "unauthorized" in err_str or "token is invalid" in err_str:
                        logger.error(f"🚨 Bot {bot.token[:10]}... is logged out/unauthorized. Disabling.")
                        if global_bot_pool:
                            global_bot_pool.mark_bot_dead_by_token(bot.token)
                    else:
                        logger.warning(f"❌ DL fail {download_target_id}: {e}")
                    TEMP_FAILED_FILES[file_id] = time.time() + 120
                    continue

                # 2. CPU (Хеши + РЕСАЙЗ)
                res, error_msg = await loop.run_in_executor(None, process_image_cpu, img_bytes)
                
                if not res:
                    logger.error(f"⚠️ Bad File {file_id}: {error_msg}")
                    # Сохраняем как ошибку, чтобы не долбить
                    sha_fail = hashlib.sha256(img_bytes).hexdigest()
                    async with db_lock:
                        await db.execute("UPDATE FileRegistry SET tags='error' WHERE file_id=?", (file_id,))
                        await db.execute("INSERT OR IGNORE INTO FileRegistry (sha256, file_id, tags, created_at) VALUES (?, ?, 'error', ?)", (sha_fail, file_id, time.time()))
                        await db.commit()
                    continue

                sha, phash, b_hash, resized_bytes = res
                tags = None
                try:
                    async with db.execute("SELECT tags FROM FileRegistry WHERE sha256 = ? AND tags IS NOT NULL AND tags != '' LIMIT 1", (sha,)) as cursor:
                        row = await cursor.fetchone()
                        if row:
                            tags = row[0]
                            logger.info(f"♻️ Skip Neuro: Tags found for SHA {sha[:8]}")
                except Exception: pass

                # 3. НЕЙРОНКА (Только если теги еще не найдены в БД)
                if tags is None:
                    tags = await get_neuro_tags(resized_bytes)
                
                if tags == "error_413":
                    tags = "error_too_large"
                
                tag_mark = "🏷️" if (tags and "error" not in tags) else "⚪"
                
                save_success = False
                has_suspicious = False # <--- ИНИЦИАЛИЗАЦИЯ

                for attempt in range(10):
                    try:
                        async with db_lock:
                            cursor = await db.execute("""
                                UPDATE FileRegistry 
                                SET tags = ?, phash = ?, blurhash = ?
                                WHERE file_id = ?
                            """, (tags, phash, b_hash, file_id))
                            
                            if cursor.rowcount == 0:
                                await db.execute("""
                                    INSERT INTO FileRegistry 
                                    (sha256, phash, file_id, thumbnail_id, file_type, created_at, blurhash, tags)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                    ON CONFLICT(sha256) DO UPDATE SET
                                        tags = excluded.tags,
                                        phash = excluded.phash
                                """, (sha, phash, file_id, None, file_type, time.time(), b_hash, tags))

                            await db.commit()
                        save_success = True
                        logger.info(f"✅ {file_type.upper()} {file_id[:8]} | {tag_mark} | Saved")
                        break
                    except Exception as e:
                        if "locked" in str(e).lower():
                            await asyncio.sleep(0.5 * (attempt + 1))
                            continue
                        logger.error(f"❌ DB Save error: {e}")
                        break
                
                # === МОДЕРАЦИЯ (Deep Check) ===
                should_deep_check = False
                
                # 1. Проверка по типу файла (видео чекаем всегда, так как теги по первому кадру могут врать)
                if file_type in ['gif', 'video_note']:
                    should_deep_check = True
                
                # 2. Проверка по тегам (если файл успешно сохранен и теги есть)
                elif save_success and tags and "error" not in tags:
                    tags_lower = tags.lower()
                    has_suspicious = any(w in tags_lower for w in SUSPICIOUS_KEYWORDS)
                    is_safe_style = any(s in tags_lower for s in SAFE_KEYWORDS)
                    
                    # Чекаем только если есть подозрительные слова И ЭТО НЕ безопасный стиль (аниме/арт)
                    if has_suspicious and not is_safe_style:
                        should_deep_check = True
                
                if should_deep_check:
                    logger.warning(f"🛡️ Triggered DEEP CHECK for {file_id}")
                    spawn_task(run_deep_check(resized_bytes, file_id))
                
                if not tags:
                    TEMP_FAILED_FILES[file_id] = time.time() + 60

            except Exception as e:
                logger.error(f"💥 Crit fail {file_id}: {e}")
                TEMP_FAILED_FILES[file_id] = time.time() + 300
            
            # Пауза между файлами (чтобы не спамить в Groq)
            await asyncio.sleep(2)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.critical(f"Loop crash: {e}", exc_info=True)
            await asyncio.sleep(30)