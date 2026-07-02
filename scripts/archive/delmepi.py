import asyncio
from common.task_manager import spawn_task
import aiosqlite
import logging
import time
import sys
import os
import signal
import hashlib
import imagehash
import math
import argparse
from io import BytesIO
from PIL import Image
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

# --- ИМПОРТЫ ПРОЕКТА ---
from common.config import DB_NAME
from common.token_pool import groq_pool
from common.bot_pool import global_bot_pool
from common.secret_redaction import install_logging_redaction
import httpx
from openai import AsyncOpenAI

PROXY_URL = "http://127.0.0.1:10808"

# --- НАСТРОЙКИ ---
CONCURRENCY_LIMIT = 1 
DB_BATCH_SIZE = 100 
GROQ_MODEL = "meta-llama/llama-4-maverick-17b-128e-instruct"
GROQ_TIMEOUT = 20.0     

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler("media_processor.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
install_logging_redaction()
logger = logging.getLogger("Processor")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("aiosqlite").setLevel(logging.WARNING)
logging.getLogger("aiogram").setLevel(logging.WARNING)

SHUTDOWN_FLAG = False

def handle_sigint(signum, frame):
    global SHUTDOWN_FLAG
    print("\n🛑 Получен сигнал остановки! Доделываем текущие задачи...")
    SHUTDOWN_FLAG = True

signal.signal(signal.SIGINT, handle_sigint)

# ==========================================
# ВСТРОЕННЫЙ BLURHASH (Pure Python)
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

    dc = factors[0]
    ac = factors[1:]

    hash_list = []
    size_flag = (components_x - 1) + (components_y - 1) * 9
    hash_list.append(encode_83(size_flag, 1))

    if len(ac) > 0:
        actual_max = max(max(abs(val) for val in band) for band in ac)
        quantised_max = int(max(0, min(82, math.floor(actual_max * 166 - 0.5))))
        max_val = (quantised_max + 1) / 166.0
        hash_list.append(encode_83(quantised_max, 1))
    else:
        max_val = 1.0
        hash_list.append(encode_83(0, 1))

    hash_list.append(encode_dc(dc))
    for factor in ac:
        hash_list.append(encode_ac(factor, max_val))

    return "".join(hash_list)

# ==========================================
# ОСНОВНАЯ ЛОГИКА
# ==========================================

async def init_db_schema():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS FileRegistry (
                sha256 TEXT PRIMARY KEY,
                phash TEXT,
                file_id TEXT NOT NULL,
                thumbnail_id TEXT,
                file_type TEXT,
                created_at REAL,
                blurhash TEXT,
                tags TEXT
            );
        """)
        try:
            await db.execute("ALTER TABLE FileRegistry ADD COLUMN tags TEXT;")
        except aiosqlite.OperationalError: pass
        try:
            await db.execute("ALTER TABLE FileRegistry ADD COLUMN phash TEXT;")
        except aiosqlite.OperationalError: pass
        try:
            await db.execute("ALTER TABLE FileRegistry ADD COLUMN blurhash TEXT;")
        except aiosqlite.OperationalError: pass
        
        await db.execute("CREATE TABLE IF NOT EXISTS FileOwners (file_id TEXT PRIMARY KEY, bot_id INTEGER NOT NULL);")
        await db.commit()

async def get_tasks(rewrite_tags=False):
    logger.info(f"🔍 Сканирование... (Rewrite: {rewrite_tags})")
    
    conn = await aiosqlite.connect(DB_NAME)
    
    file_owners = {}
    try:
        async with conn.execute("SELECT file_id, bot_id FROM FileOwners") as cursor:
            async for row in cursor:
                file_owners[row[0]] = row[1]
    except: pass

    # --- 1. Собираем черный список тамбнейлов ---
    known_thumbnails = set()
    try:
        async with conn.execute("SELECT thumbnail_id FROM FileRegistry WHERE thumbnail_id IS NOT NULL") as cursor:
            async for row in cursor:
                if row[0]: known_thumbnails.add(row[0])
        logger.info(f"🗑️ Найдено {len(known_thumbnails)} тамбнейлов для исключения.")
    except: pass

    tasks_to_process = []
    
    # БЕРЕМ: 'image' (старые оригиналы) и 'document' (файлы-оригиналы)
    # ИГНОРИРУЕМ: 'photo' (сжатые), 'sticker', 'video'
    target_types = ('image', 'document')
    placeholders = ", ".join(["?"] * len(target_types))

    query_registry = f"""
        SELECT file_id
        FROM FileRegistry
        WHERE file_type IN ({placeholders})
        AND (tags IS NULL OR phash IS NULL OR blurhash IS NULL)
    """
    if rewrite_tags:
        query_registry = f"SELECT file_id FROM FileRegistry WHERE file_type IN ({placeholders})"
        
    async with conn.execute(query_registry, target_types) as cursor:
        async for row in cursor:
            fid = row[0]
            if fid in known_thumbnails: continue
            tasks_to_process.append({
                'original_file_id': fid,
                'owner_bot_id': file_owners.get(fid)
            })

    # Дополнительный поиск в постах (для страховки)
    async with conn.execute(f"""
        SELECT DISTINCT json_extract(j.value, '$.original_file_id') AS file_id
        FROM Posts p, json_each(p.content, '$.files') j
        WHERE json_extract(j.value, '$.type') IN ({placeholders})
          AND json_extract(j.value, '$.original_file_id') IS NOT NULL
          AND json_extract(j.value, '$.original_file_id') NOT IN (SELECT file_id FROM FileRegistry)
    """, target_types) as cursor:
        async for row in cursor:
            fid = row[0]
            if fid in known_thumbnails: continue
            tasks_to_process.append({
                'original_file_id': fid,
                'owner_bot_id': file_owners.get(fid)
            })

    await conn.close()
    
    unique_tasks = list({t['original_file_id']: t for t in tasks_to_process}.values())
    
    # Исправляем статистику: считаем не по JSON постов (там каша), а по реальным записям в реестре
    conn_stat = await aiosqlite.connect(DB_NAME)
    async with conn_stat.execute(f"SELECT COUNT(*) FROM FileRegistry WHERE file_type IN ({placeholders})", target_types) as cursor:
        total_valid_images = (await cursor.fetchone())[0]
    await conn_stat.close()

    logger.info(f"📊 Всего оригиналов в базе (image+document): {total_valid_images}")
    logger.info(f"🛠 Требуют обработки: {len(unique_tasks)}")
    
    return unique_tasks

def cpu_heavy_calculations(image_bytes):
    try:
        if len(image_bytes) == 0: return None, "Empty bytes"

        # 1. SHA256 (Primary Key, обязателен)
        sha = hashlib.sha256(image_bytes).hexdigest()

        # 2. PIL
        try:
            img = Image.open(BytesIO(image_bytes))
            img.load()
            if img.mode != 'RGB': img = img.convert('RGB')
        except Exception as e:
            return None, f"PIL Error: {e}"

        # 3. pHash
        phash = str(imagehash.phash(img))
        
        # 4. BlurHash
        try:
            small = img.resize((32, 32), Image.Resampling.BILINEAR)
            b_hash = encode_blurhash_internal(small, 4, 3)
        except Exception as e:
            return None, f"BlurHash Error: {e}"

        return (sha, phash, b_hash), None

    except Exception as e:
        return None, f"Unknown CPU Error: {e}"

async def get_neuro_tags(image_bytes):
    if not groq_pool.tokens:
        logger.error("❌ [Groq] Нет токенов!")
        return None

    import base64
    b64 = base64.b64encode(image_bytes).decode('utf-8')
    url = f"data:image/jpeg;base64,{b64}"
    
    # Универсальный промпт
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

    for i in range(3):
        if SHUTDOWN_FLAG: return None
        token = groq_pool.get_token()
        if not token: return None
        
        try:
            transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
            http_client = httpx.AsyncClient(
                proxy=PROXY_URL,
                transport=transport,
                verify=False
            )
            client = AsyncOpenAI(
                api_key=token,
                base_url="https://api.groq.com/openai/v1",
                timeout=GROQ_TIMEOUT,
                http_client=http_client
            )
            resp = await client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": url}}]}],
                max_tokens=250
            )
            await http_client.aclose()
            return resp.choices[0].message.content.strip()
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "limit" in err:
                await asyncio.sleep(2)
                continue
            elif "400" in err:
                return None
            else:
                logger.error(f"💥 [Groq] Error: {e}")
            continue
            
    return None

async def worker(sem, input_queue, output_queue):
    loop = asyncio.get_running_loop()
    
    while not SHUTDOWN_FLAG:
        try:
            task = input_queue.get_nowait()
        except asyncio.QueueEmpty:
            break
            
        file_id = task.get('original_file_id')
        owner_id = task.get('owner_bot_id')
        skip_tags = task.get('skip_tags', False)
        
        bot = None
        if owner_id: bot = global_bot_pool.get_bot_by_id(owner_id)
        if not bot: bot = global_bot_pool.get_main_bot()
        
        if not bot:
             input_queue.task_done()
             continue

        async with sem:
            try:
                # 1. Скачивание
                f_info = await bot.get_file(file_id)
                f_obj = await bot.download_file(f_info.file_path)
                
                if hasattr(f_obj, 'getvalue'): img_data = f_obj.getvalue()
                else: img_data = f_obj.read()
                
                # 2. Хеши
                calc_res, error_msg = await loop.run_in_executor(None, cpu_heavy_calculations, img_data)
                
                if calc_res:
                    sha, phash, b_hash = calc_res
                    
                    # 3. Теги (если нужно)
                    tags = None
                    if not skip_tags:
                        tags = await get_neuro_tags(img_data)
                    
                    await output_queue.put({
                        'sha256': sha,
                        'file_id': file_id,
                        'phash': phash,
                        'blurhash': b_hash,
                        'tags': tags,
                        'file_type': 'image',
                        'thumbnail_id': task.get('thumbnail_file_id')
                    })
                    
                    tag_mark = "🏷️" if tags else "❌"
                    log_sha = sha[:20] + "..." if sha else "None"
                    log_phash = phash[:20] + "..." if phash else "None"
                    log_blur = b_hash[:20] + "..." if b_hash else "None"

                    logger.info(
                        f"✅ {file_id[:10]} | "
                        f"SHA: {log_sha} | "
                        f"pH: {log_phash} | "
                        f"Blur: {log_blur} | "
                        f"{tag_mark}"
                    )
                else:
                    logger.error(f"⚠️ Ошибка данных {file_id}: {error_msg}")
                    
            except Exception as e:
                logger.error(f"💥 Сбой {file_id}: {e}")
            
            await asyncio.sleep(0.1)
            input_queue.task_done()

async def db_writer(queue):
    logger.info("💾 DB Writer запущен.")
    conn = await aiosqlite.connect(DB_NAME)
    await conn.execute("PRAGMA journal_mode=WAL;")
    await conn.execute("PRAGMA busy_timeout = 10000;") 
    
    batch = []
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=2.0)
                batch.append(item)
                queue.task_done()
            except asyncio.TimeoutError:
                pass 
            
            if len(batch) >= DB_BATCH_SIZE or (SHUTDOWN_FLAG and batch):
                try:
                    data_tuples = [(
                        x['sha256'], x['phash'], x['file_id'], x['thumbnail_id'], 
                        x['file_type'], time.time(), x['blurhash'], x['tags']
                    ) for x in batch]
                    
                    # COALESCE ВАЖЕН:
                    # Если tags = NULL (пришел None из Python), то оставляем старое значение tags.
                    # Если tags != NULL (пришел новый тег), то обновляем.
                    # То же самое для хешей (хотя они обычно всегда есть).
                    await conn.executemany("""
                        INSERT INTO FileRegistry 
                        (sha256, phash, file_id, thumbnail_id, file_type, created_at, blurhash, tags)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(sha256) DO UPDATE SET
                            phash = COALESCE(excluded.phash, phash),
                            blurhash = COALESCE(excluded.blurhash, blurhash),
                            tags = COALESCE(excluded.tags, tags),
                            file_id = excluded.file_id
                    """, data_tuples)
                    await conn.commit()
                    logger.info(f"💾 Сохранена пачка: {len(batch)} шт.")
                    batch = []
                except Exception as e:
                    logger.error(f"DB Write Error: {e}")
            
            if SHUTDOWN_FLAG and queue.empty() and not batch:
                break
    finally:
        await conn.close()
        logger.info("💾 DB Writer остановлен.")

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rewrite", action="store_true", help="Принудительная перезапись ВСЕХ тегов")
    args = parser.parse_args()

    print(f"🚀 ЗАПУСК PROCESSOR | Threads: {CONCURRENCY_LIMIT}")
    print(f"🔄 Режим: {'Полная перезапись' if args.rewrite else 'Доработка пропущенного'}")
    
    if not global_bot_pool.all_bots:
        logger.error("❌ Пул ботов пуст! Проверь .env")
        return

    await init_db_schema()
    
    files_to_process = await get_tasks(rewrite_tags=args.rewrite)
    if not files_to_process:
        print("🎉 Нечего обрабатывать.")
        await global_bot_pool.close_all()
        return

    input_queue = asyncio.Queue()
    output_queue = asyncio.Queue()
    
    for f in files_to_process:
        input_queue.put_nowait(f)
        
    sem = asyncio.Semaphore(CONCURRENCY_LIMIT)
    writer_task = spawn_task(db_writer(output_queue))
    
    workers = [
        spawn_task(worker(sem, input_queue, output_queue))
        for _ in range(CONCURRENCY_LIMIT)
    ]
    
    while not input_queue.empty() and not SHUTDOWN_FLAG:
        await asyncio.sleep(1)
        
    if not SHUTDOWN_FLAG:
        await input_queue.join()
    
    for w in workers: w.cancel()
    await writer_task
    
    await global_bot_pool.close_all()
    print("\n🏁 Готово.")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
