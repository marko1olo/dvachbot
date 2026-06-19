import asyncio
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

# === НАСТРОЙКИ ===
logger = logging.getLogger("tagger")
PROXY_URL = "http://127.0.0.1:10808"
GROQ_MODEL = "meta-llama/llama-4-maverick-17b-128e-instruct"
GROQ_TIMEOUT = 40.0
BATCH_SIZE = 1  # СТРОГО ПО ОДНОМУ, чтобы не насиловать ключи

GROQ_COOLDOWN_UNTIL = 0
TEMP_FAILED_FILES = {}

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

# ==========================================
# НЕЙРОНКА (GROQ)
# ==========================================
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
    
    prompt = (
        "Analyze the image content comprehensively. It can be an illustration, a screenshot, a photo, a chart, or a meme. "
        "Generate a diverse list of 20-40 descriptive tags based on the content type:\n"
        "1. If Art/Anime/NSFW: Describe character features, clothing (or lack of), pose, action, artistic style.\n"
        "2. If Screenshot/Meme: Describe UI elements, visible text topics, visual jokes, platform (e.g., 4chan, twitter).\n"
        "3. If Chart/Graph: Describe data type, visual style, key topics.\n"
        "4. If Photo: Describe objects, scenery, lighting, realism.\n"
        "Always include colors and general mood. "
        "Output ONLY the comma-separated list of English tags. No intro, no sentences."
    )

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
                    client = AsyncOpenAI(api_key=token, base_url="https://api.groq.com/openai/v1", http_client=http_client)
                    resp = await client.chat.completions.create(
                        model=GROQ_MODEL,
                        messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": url}}]}],
                        max_tokens=250
                    )
                    content = resp.choices[0].message.content
                    if content:
                        return content.strip().rstrip('.,')
            except Exception as e:
                err_str = str(e).lower()
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
    # 1. Основная очередь из реестра
    query_registry = f"""
        SELECT file_id, file_type
        FROM FileRegistry
        WHERE file_type IN ('image', 'photo') 
        AND (tags IS NULL OR tags = '')
        ORDER BY created_at DESC
        LIMIT {BATCH_SIZE * 5}
    """
    try:
        async with db.execute(query_registry) as cursor:
            async for row in cursor:
                tasks.append({'fid': row[0], 'type': row[1], 'bot_id': file_owners.get(row[0])})
    except Exception as e:
        logger.error(f"DB Error getting registry tasks: {e}")

    # 2. Поиск пропущенных файлов (Gaps) в последних 200 постах
    if len(tasks) < BATCH_SIZE:
        query_gaps = """
            SELECT DISTINCT json_extract(j.value, '$.original_file_id') as fid, json_extract(j.value, '$.type') as ftype
            FROM Posts p, json_each(p.content, '$.files') j
            WHERE p.post_num > (SELECT MAX(post_num) - 250 FROM Posts)
              AND ftype IN ('image', 'photo')
              AND fid NOT IN (SELECT file_id FROM FileRegistry)
            LIMIT 10
        """
        try:
            async with db.execute(query_gaps) as cursor:
                async for row in cursor:
                    if not any(t['fid'] == row[0] for t in tasks):
                        tasks.append({'fid': row[0], 'type': row[1], 'bot_id': file_owners.get(row[0])})
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

            bot = global_bot_pool.get_bot_by_id(bot_id) if bot_id else global_bot_pool.get_main_bot()
            if not bot:
                TEMP_FAILED_FILES[file_id] = time.time() + 300
                continue

            try:
                # 1. СКАЧИВАНИЕ
                try:
                    f_info = await bot.get_file(file_id)
                    f_obj = await bot.download_file(f_info.file_path)
                    img_bytes = f_obj.read() if hasattr(f_obj, 'read') else f_obj
                except TelegramBadRequest:
                    logger.error(f"🗑️ File {file_id} deleted. Marking error.")
                    async with db_lock:
                        await db.execute("UPDATE FileRegistry SET tags='error' WHERE file_id=?", (file_id,))
                        dummy_sha = f"del_{file_id}"
                        await db.execute("INSERT OR IGNORE INTO FileRegistry (sha256, file_id, tags, created_at) VALUES (?, ?, 'error', ?)", (dummy_sha, file_id, time.time()))
                        await db.commit()
                    continue
                except Exception as e:
                    logger.warning(f"❌ DL fail {file_id}: {e}")
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
                tags_preview = "No tags"
                if tags and "error" not in tags:
                    parts = [t.strip() for t in tags.split(',') if t.strip()]
                    tags_preview = ", ".join(parts[:3])
                save_success = False
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
                        logger.info(f"✅ {file_id[:8]} | {tag_mark} | Saved to DB")
                        break
                    except Exception as e:
                        if "locked" in str(e).lower():
                            await asyncio.sleep(0.5 * (attempt + 1))
                            continue
                        logger.error(f"❌ DB Save error for {file_id[:8]}: {e}")
                        break
                
                if not save_success:
                    logger.warning(f"⚠️ Failed to save tags for {file_id[:8]} after all retries.")                
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