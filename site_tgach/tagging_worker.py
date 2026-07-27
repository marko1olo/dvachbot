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
import os
import tempfile
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
logger.setLevel(logging.INFO)
if not logger.handlers:
    _sh = logging.StreamHandler()
    _sh.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_sh)
logger.propagate = True

PROXY_URL = "http://127.0.0.1:10808"
GROQ_MODEL = "qwen/qwen3.6-27b"
GROQ_TIMEOUT = 40.0
BATCH_SIZE = 1  # СТРОГО ПО ОДНОМУ, чтобы не насиловать ключи

GROQ_COOLDOWN_UNTIL = 0
TEMP_FAILED_FILES = {}

SUSPICIOUS_KEYWORDS = {'child', 'kid', 'toddler', 'infant', 'baby', 'teen', 'underage', 'young girl', 'little girl'}
SAFE_KEYWORDS = {'anime', 'illustration', 'sketch', 'digital art', 'painting', '3d_render', 'cartoon', 'manga'}

# Один висящий get_file/download_file раньше мог застопорить весь цикл тегирования
# на минуты, потому что фолбэк перебирает ВСЕ боты пула подряд.
DOWNLOAD_TIMEOUT_PER_BOT = 45.0
DOWNLOAD_TOTAL_TIMEOUT = 120.0


def _remove_temp_file(path: str | None) -> None:
    """Best-effort удаление временного файла; тихо игнорирует отсутствие."""
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass

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
def extract_video_frame_cpu(video_bytes: bytes) -> bytes | None:
    """
    Извлекает 1 кадр из видеофайла (MP4, GIF, WebM) с помощью ffmpeg.
    Возвращает JPEG байты кадра или None при ошибке.
    """
    if not video_bytes:
        return None
    import subprocess

    tmp_v_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_v:
            tmp_v_path = tmp_v.name
            tmp_v.write(video_bytes)

        cmd = [
            "ffmpeg", "-y", "-ss", "00:00:00.500",
            "-i", tmp_v_path,
            "-vframes", "1",
            "-f", "image2pipe",
            "-vcodec", "mjpeg",
            "-"
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        if res.returncode == 0 and res.stdout and len(res.stdout) > 100:
            return res.stdout
    except FileNotFoundError:
        logger.warning("⚠️ [TAGGER] ffmpeg не найден в PATH, кадры из видео не извлекаются.")
    except subprocess.TimeoutExpired:
        # Раньше os.remove стоял ПОСЛЕ subprocess.run, поэтому таймаут
        # (частый на тяжёлых видео) навсегда оставлял mp4 в %TEMP%.
        logger.warning(f"⚠️ [TAGGER] ffmpeg timeout на {len(video_bytes)} байт видео.")
    except Exception as e:
        logger.warning(f"⚠️ [TAGGER] ffmpeg frame extraction failed: {e}")
    finally:
        _remove_temp_file(tmp_v_path)
    return None

def process_image_cpu(image_bytes):
    """
    1. Считает хеши (SHA, pHash, Blur).
    2. Извлекает кадр из видео, если это видеофайл.
    3. Ресайзит картинку для нейронки.
    """
    try:
        Image.MAX_IMAGE_PIXELS = 49_000_000 

        if not image_bytes: return None, "Empty bytes"
        
        # 1. SHA256 (всегда)
        sha = hashlib.sha256(image_bytes).hexdigest()

        # 1.1 Проверка сигнатуры Lottie Telegram стикера (.tgs gzipped json)
        if image_bytes.startswith(b'\x1f\x8b'):
            return (sha, None, None, None), "lottie_sticker"

        # 2. Открываем PIL
        img = None
        try:
            img = Image.open(io.BytesIO(image_bytes))
            img.load()
            if img.mode != 'RGB': img = img.convert('RGB')
        except Image.DecompressionBombError:
            return None, "Decompression Bomb Detected"
        except Exception as e:
            # Если это видео или неподдерживаемый формат — пробуем извлечь кадр через ffmpeg
            frame_bytes = extract_video_frame_cpu(image_bytes)
            if frame_bytes:
                try:
                    img = Image.open(io.BytesIO(frame_bytes))
                    img.load()
                    if img.mode != 'RGB': img = img.convert('RGB')
                except Exception:
                    return (sha, None, None, None), f"unsupported_format: {e}"
            else:
                return (sha, None, None, None), f"unsupported_format: {e}"

        try:
            # 3. pHash
            phash = str(imagehash.phash(img))

            # 4. BlurHash
            small_blur = None
            try:
                small_blur = img.resize((32, 32), Image.Resampling.BILINEAR)
                b_hash = encode_blurhash_internal(small_blur, 4, 3)
            except Exception:
                b_hash = None
            finally:
                if small_blur is not None:
                    small_blur.close()

            # 5. ПОДГОТОВКА ДЛЯ НЕЙРОНКИ (Ресайз)
            # Groq не любит файлы > 4MB. Ужимаем до 1024px по большей стороне.
            MAX_SIZE = 1024
            if max(img.size) > MAX_SIZE:
                img.thumbnail((MAX_SIZE, MAX_SIZE), Image.Resampling.LANCZOS)

            # Сохраняем в JPEG (легче чем PNG)
            with io.BytesIO() as buffer:
                img.save(buffer, format="JPEG", quality=85)
                resized_bytes = buffer.getvalue()

            return (sha, phash, b_hash, resized_bytes), None
        finally:
            # Воркер крутится 24/7: незакрытый Image держит буфер декодера
            # на каждый обработанный файл.
            img.close()

    except Exception as e:
        return None, f"CPU Error: {type(e).__name__}: {e}"

@api_retry
async def _execute_tagging(client, model, messages, max_tokens):
    return await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens
    )

async def get_neuro_tags(resized_image_bytes: bytes) -> str | None:
    """
    Получает теги для изображения, используя основной каскад Vision (Gemini / Groq).
    """
    if not resized_image_bytes:
        return None

    tmp_path = ""
    try:
        from site_tgach.vision import describe_image
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name
            tmp.write(resized_image_bytes)

        return await describe_image(
            tmp_path, caption="Generate tags for this image", is_passive=False, source="TAGGER"
        )
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.warning(f"⚠️ [TAGGER] Vision analysis error: {type(e).__name__}: {e}")
        return None
    finally:
        # Раньше удаление стояло после await: любое исключение в describe_image
        # оставляло jpg в %TEMP% навсегда.
        _remove_temp_file(tmp_path)

# ==========================================
# ПОЛУЧЕНИЕ ЗАДАЧ
# ==========================================
async def get_tasks(db) -> list[dict]:
    tasks = []
    # 1. Из реестра (все необработанные файлы без ограничения по времени)
    query_registry = f"""
        SELECT file_id, file_type, thumbnail_id
        FROM FileRegistry
        WHERE file_type IN ('image', 'photo', 'video', 'animation', 'gif', 'video_note', 'sticker', 'document') 
        AND (tags IS NULL OR tags = '')
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
                    'bot_id': None
                })
    except Exception as e:
        logger.error(f"DB Error getting registry tasks: {e}")

    # 2. Поиск пропущенных файлов (Gaps) в последних 250 постах (включая видео, фото, стикеры и альбомы)
    if len(tasks) < BATCH_SIZE:
        query_gaps_files = """
            SELECT DISTINCT 
                json_extract(j.value, '$.original_file_id') as fid, 
                json_extract(j.value, '$.type') as ftype,
                json_extract(j.value, '$.thumbnail_file_id') as thumb_id
            FROM Posts p, json_each(p.content, '$.files') j
            WHERE p.post_num > (SELECT COALESCE(MAX(post_num), 0) - 250 FROM Posts)
              AND ftype IN ('image', 'photo', 'video', 'animation', 'gif', 'video_note', 'sticker', 'document')
              AND fid IS NOT NULL
              AND fid NOT IN (SELECT file_id FROM FileRegistry)
            LIMIT 10
        """
        query_gaps_single = """
            SELECT DISTINCT 
                json_extract(p.content, '$.file_id') as fid, 
                json_extract(p.content, '$.type') as ftype,
                NULL as thumb_id
            FROM Posts p
            WHERE p.post_num > (SELECT COALESCE(MAX(post_num), 0) - 250 FROM Posts)
              AND ftype IN ('image', 'photo', 'video', 'animation', 'gif', 'video_note', 'sticker', 'document')
              AND fid IS NOT NULL
              AND fid NOT IN (SELECT file_id FROM FileRegistry)
            LIMIT 10
        """
        try:
            async with db.execute(query_gaps_files) as cursor:
                async for row in cursor:
                    if row[0] and not any(t['fid'] == row[0] for t in tasks):
                        tasks.append({'fid': row[0], 'type': row[1] or 'photo', 'thumb_id': row[2], 'bot_id': None})
            async with db.execute(query_gaps_single) as cursor:
                async for row in cursor:
                    if row[0] and not any(t['fid'] == row[0] for t in tasks):
                        tasks.append({'fid': row[0], 'type': row[1] or 'photo', 'thumb_id': row[2], 'bot_id': None})
        except Exception as e:
            logger.error(f"Gaps query error: {e}")

    tasks = tasks[:BATCH_SIZE]

    # 3. Populate bot_id for the tasks
    if tasks:
        fids = [t['fid'] for t in tasks]
        placeholders = ','.join(['?'] * len(fids))
        try:
            query_owners = f"SELECT file_id, bot_id FROM FileOwners WHERE file_id IN ({placeholders})"
            async with db.execute(query_owners, fids) as cursor:
                owners_map = {}
                async for row in cursor:
                    owners_map[row[0]] = row[1]
                for t in tasks:
                    t['bot_id'] = owners_map.get(t['fid'])
        except Exception as e:
            logger.error(f"DB Error getting file owners: {e}")

    return tasks

def _build_download_candidates(primary_bot) -> list:
    """Порядок ботов для попытки скачивания: владелец файла -> главный -> остальные."""
    bots_to_try = []
    if primary_bot:
        bots_to_try.append(primary_bot)

    main_bot = global_bot_pool.get_main_bot() if global_bot_pool else None
    if main_bot and main_bot not in bots_to_try:
        bots_to_try.append(main_bot)

    all_bots = global_bot_pool.get_all_active_bots() if global_bot_pool else []
    for b in all_bots:
        if b not in bots_to_try:
            bots_to_try.append(b)
    return bots_to_try


async def _download_via_bot(bot, file_id: str) -> bytes | None:
    """Одна попытка скачивания конкретным ботом под жёстким таймаутом."""
    f_info = await asyncio.wait_for(bot.get_file(file_id), timeout=DOWNLOAD_TIMEOUT_PER_BOT)
    file_path = getattr(f_info, "file_path", None)
    if not file_path:
        return None
    f_obj = await asyncio.wait_for(bot.download_file(file_path), timeout=DOWNLOAD_TIMEOUT_PER_BOT)
    return f_obj.read() if hasattr(f_obj, 'read') else f_obj


async def download_file_with_fallback(file_id: str, primary_bot=None):
    """
    Пробует скачать файл каждым доступным ботом.

    Таймауты обязательны: без них один зависший HTTP-запрос останавливал весь
    цикл тегирования, а перебор всего пула умножал задержку на число ботов.
    """
    bots_to_try = _build_download_candidates(primary_bot)
    if not bots_to_try:
        return None, None

    deadline = time.monotonic() + DOWNLOAD_TOTAL_TIMEOUT

    for b in bots_to_try:
        if time.monotonic() >= deadline:
            logger.warning(f"⏱️ [TAGGER] Общий бюджет скачивания исчерпан для {file_id[:15]}.")
            break
        try:
            img_bytes = await _download_via_bot(b, file_id)
            if img_bytes:
                return img_bytes, b
        except asyncio.TimeoutError:
            logger.warning(f"⏱️ [TAGGER] Таймаут скачивания {file_id[:15]}, пробую следующего бота.")
            continue
        except asyncio.CancelledError:
            raise
        except TelegramBadRequest:
            continue
        except Exception as e:
            err_str = str(e).lower()
            if "logged out" in err_str or "unauthorized" in err_str or "token is invalid" in err_str:
                if global_bot_pool:
                    global_bot_pool.mark_bot_dead_by_token(b.token)
            continue
    return None, None

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

            # Определяем, что качать (для видео предпочтительно превью, иначе сам файл)
            download_target_id = thumb_id if (thumb_id and file_type in {'video', 'animation', 'gif', 'video_note'}) else file_id

            try:
                # 1. СКАЧИВАНИЕ С РЕТРАЕМ ПО ВСЕМ БОТАМ
                img_bytes, active_bot = await download_file_with_fallback(download_target_id, primary_bot=bot)
                
                # Если превью не удалось скачать для видео, пробуем скачать сам файл видео
                if not img_bytes and download_target_id != file_id:
                    download_target_id = file_id
                    img_bytes, active_bot = await download_file_with_fallback(download_target_id, primary_bot=bot)

                if not img_bytes:
                    logger.warning(f"❌ DL fail for {file_id[:15]} across all bots. Skipping temporarily.")
                    TEMP_FAILED_FILES[file_id] = time.time() + 180
                    continue

                # 2. CPU (Хеши + РЕСАЙЗ)
                res, error_msg = await loop.run_in_executor(None, process_image_cpu, img_bytes)
                
                if error_msg == "lottie_sticker":
                    logger.info(f"🎨 [BG_TAGGER] Lottie Sticker {file_id[:12]} -> marked as 'sticker_animated'")
                    async with db_lock:
                        await db.execute("UPDATE FileRegistry SET tags='sticker_animated' WHERE file_id=?", (file_id,))
                        await db.commit()
                    continue
                elif error_msg and "unsupported_format" in error_msg:
                    logger.info(f"📁 [BG_TAGGER] Media {file_id[:12]} -> marked as 'format_unsupported'")
                    async with db_lock:
                        await db.execute("UPDATE FileRegistry SET tags='format_unsupported' WHERE file_id=?", (file_id,))
                        await db.commit()
                    continue
                elif not res:
                    logger.error(f"⚠️ Bad File {file_id}: {error_msg}")
                    # Сохраняем как ошибку, чтобы не долбить
                    sha_fail = hashlib.sha256(img_bytes).hexdigest()
                    async with db_lock:
                        await db.executemany("UPDATE FileRegistry SET tags='error' WHERE file_id=?", [(file_id,)])
                        await db.executemany("INSERT OR IGNORE INTO FileRegistry (sha256, file_id, tags, created_at) VALUES (?, ?, 'error', ?)", [(sha_fail, file_id, time.time())])
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
                        logger.info(f"🖼 [BG_TAGGER] ✅ {file_type.upper()} {file_id[:12]} | {tag_mark} | Tags: '{tags[:200] if tags else 'none'}...'")
                        break
                    except Exception as e:
                        if "locked" in str(e).lower():
                            await asyncio.sleep(0.5 * (attempt + 1))
                            continue
                        logger.error(f"❌ [BG_TAGGER] DB Save error for {file_id[:12]}: {e}")
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