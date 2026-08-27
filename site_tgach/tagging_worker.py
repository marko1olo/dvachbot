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
import re
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
# Импорты проекта
from common.db_pool import get_pool, db_lock, db_sleep, db_transaction, execute_with_retry
from common.bot_pool import global_bot_pool
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramRetryAfter,
    TelegramForbiddenError,
    TelegramUnauthorizedError,
    TelegramAPIError,
    TelegramNetworkError,
)

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

PROXY_URL = os.getenv("PROXY_URL") or os.getenv("HTTPS_PROXY") or None
GROQ_TIMEOUT = 40.0
BATCH_SIZE = 1  # СТРОГО ПО ОДНОМУ, чтобы не насиловать ключи

GROQ_COOLDOWN_UNTIL = 0
TEMP_FAILED_FILES = {}

SUSPICIOUS_KEYWORDS = {
    "child",
    "kid",
    "toddler",
    "infant",
    "baby",
    "teen",
    "underage",
    "young girl",
    "little girl",
}
SAFE_KEYWORDS = {
    "anime",
    "illustration",
    "sketch",
    "digital art",
    "painting",
    "3d_render",
    "cartoon",
    "manga",
}

MUSIC_EXTENSIONS = (
    '.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac', '.opus',
    '.wma', '.aiff', '.alac', '.mid', '.midi', '.oga'
)

AUDIO_MIME_TYPES = (
    'audio/',
    'application/ogg',
    'application/x-ogg',
)


def is_audio_media(file_type: str = None, mime_type: str = None, filename: str = None, data: bytes = None) -> bool:
    """Определяет, является ли медиафайл аудио/музыкой по типу, mime, расширению пути или сигнатуре."""
    if file_type and str(file_type).lower() in ('audio', 'voice'):
        return True

    if mime_type:
        m = str(mime_type).lower()
        if any(m.startswith(amt) or m == amt for amt in AUDIO_MIME_TYPES):
            return True

    if filename:
        fn_lower = str(filename).lower()
        if any(fn_lower.endswith(ext) for ext in MUSIC_EXTENSIONS):
            return True
        if "/music/" in fn_lower or "/voice/" in fn_lower:
            return True

    if data and len(data) >= 12:
        # ID3 (mp3)
        if data.startswith(b"ID3"):
            return True
        # MP3 sync word (11 bits set: 0xFF followed by 0xE0-0xFF)
        if data[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
            return True
        # FLAC
        if data.startswith(b"fLaC"):
            return True
        # OGG
        if data.startswith(b"OggS"):
            return True
        # RIFF WAVE
        if data.startswith(b"RIFF") and data[8:12] == b"WAVE":
            return True
        # M4A / AAC
        if data[4:8] == b"ftyp" and data[8:12] in (b"M4A ", b"mp42", b"isom") and not (b"avc1" in data[:64] or b"mp41" in data[:64]):
            return True
        if data[:2] in (b"\xff\xf1", b"\xff\xf9"):
            return True

    return False

# Оптимизированные таймауты скачивания:
# get_file — легкий JSON-запрос метаданных (до 6 секунд).
# download_file — скачивание потока байт файла (до 15 секунд).
# Общий лимит на весь процесс скачивания файла со всеми ботами — 30 секунд.
GET_FILE_TIMEOUT_PER_BOT = 6.0
DOWNLOAD_DATA_TIMEOUT_PER_BOT = 15.0
DOWNLOAD_TIMEOUT_PER_BOT = 18.0
DOWNLOAD_TOTAL_TIMEOUT = 30.0
MAX_FILE_SIZE_BOT_API = 20 * 1024 * 1024  # 20 МБ — жесткий лимит Telegram Bot API


def _remove_temp_file(path: str | None) -> None:
    """Best-effort удаление временного файла; тихо игнорирует отсутствие."""
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        import traceback; traceback.print_exc()


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
    return "".join(
        chars[(value // (83 ** (length - i))) % 83] for i in range(1, length + 1)
    )


def encode_dc(value):
    rounded = [int(min(255, max(0, v * 255 + 0.5))) for v in value]
    return encode_83(rounded[0] << 16 | rounded[1] << 8 | rounded[2], 4)


def encode_ac(value, max_val):
    quant = [
        int(max(0, min(18, math.floor(sign_pow(v / max_val, 0.5) * 9 + 9.5))))
        for v in value
    ]
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
            "ffmpeg",
            "-y",
            "-ss",
            "00:00:00.500",
            "-i",
            tmp_v_path,
            "-vframes",
            "1",
            "-f",
            "image2pipe",
            "-vcodec",
            "mjpeg",
            "-",
        ]
        res = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15
        )
        if res.returncode == 0 and res.stdout and len(res.stdout) > 100:
            return res.stdout
            
        # Если провалилось (возможно видео короче 0.5с), пробуем 00:00:00.000
        cmd[3] = "00:00:00.000"
        res2 = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        if res2.returncode == 0 and res2.stdout and len(res2.stdout) > 100:
            return res2.stdout
    except FileNotFoundError:
        logger.warning(
            "⚠️ [TAGGER] ffmpeg не найден в PATH, кадры из видео не извлекаются."
        )
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

        if not image_bytes:
            return None, "Empty bytes"

        # 1. SHA256 (всегда)
        sha = hashlib.sha256(image_bytes).hexdigest()

        # 1.1 Проверка сигнатуры Lottie Telegram стикера (.tgs gzipped json)
        if image_bytes.startswith(b"\x1f\x8b"):
            return (sha, None, None, None), "lottie_sticker"

        # 1.2 Проверка сигнатуры аудио (MP3, FLAC, OGG, WAV, etc.)
        if is_audio_media(data=image_bytes):
            return (sha, None, None, None), "audio_media"

        # 2. Открываем PIL
        img = None
        try:
            img = Image.open(io.BytesIO(image_bytes))
            img.load()
            if img.mode != "RGB":
                img = img.convert("RGB")
        except Image.DecompressionBombError:
            return None, "Decompression Bomb Detected"
        except Exception as e:
            # Если это видео или неподдерживаемый формат — пробуем извлечь кадр через ffmpeg
            frame_bytes = extract_video_frame_cpu(image_bytes)
            if frame_bytes:
                try:
                    img = Image.open(io.BytesIO(frame_bytes))
                    img.load()
                    if img.mode != "RGB":
                        img = img.convert("RGB")
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
            tmp_path,
            caption="Generate tags for this image",
            is_passive=False,
            source="TAGGER",
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
# ==========================================
# ПОЛУЧЕНИЕ ЗАДАЧ
# ==========================================
async def get_tasks(db, exclude_fids: set | list | None = None) -> list[dict]:
    tasks = []
    exclude_list = list(exclude_fids) if exclude_fids else []
    
    # 1. Из реестра (все необработанные файлы без ограничения по времени)
    if exclude_list:
        ex_slice = exclude_list[:100]
        placeholders = ",".join(["?"] * len(ex_slice))
        query_registry = f"""
            SELECT file_id, file_type, thumbnail_id
            FROM FileRegistry
            WHERE (tags IS NULL OR tags = '')
              AND file_id NOT IN ({placeholders})
            ORDER BY created_at DESC
            LIMIT 50
        """
        params = tuple(ex_slice)
    else:
        query_registry = """
            SELECT file_id, file_type, thumbnail_id
            FROM FileRegistry
            WHERE (tags IS NULL OR tags = '')
            ORDER BY created_at DESC
            LIMIT 50
        """
        params = ()

    async def _fetch_registry():
        reg_tasks = []
        async with db.execute(query_registry, params) as cursor:
            async for row in cursor:
                if row[0] and (not exclude_list or row[0] not in exclude_list):
                    reg_tasks.append(
                        {"fid": row[0], "type": row[1], "thumb_id": row[2], "bot_id": None}
                    )
        return reg_tasks

    try:
        tasks = await execute_with_retry(_fetch_registry, max_retries=3, base_delay=0.1)
    except Exception as e:
        logger.error(f"DB Error getting registry tasks: {e}", exc_info=True)
        tasks = []

    # 2. Поиск пропущенных файлов (Gaps) в последних 250 постах (включая видео, фото, стикеры и альбомы)
    if len(tasks) < BATCH_SIZE:
        query_gaps_files = """
            SELECT DISTINCT 
                json_extract(j.value, '$.original_file_id') as fid, 
                json_extract(j.value, '$.type') as ftype,
                json_extract(j.value, '$.thumbnail_file_id') as thumb_id,
                COALESCE(json_extract(j.value, '$.file_name'), json_extract(j.value, '$.filename')) as fname,
                json_extract(j.value, '$.mime_type') as fmime
            FROM Posts p, json_each(p.content, '$.files') j
            WHERE p.post_num > (SELECT COALESCE(MAX(post_num), 0) - 250 FROM Posts)
              AND ftype IN ('image', 'photo', 'video', 'animation', 'gif', 'video_note', 'sticker', 'document')
              AND fid IS NOT NULL
              AND fid NOT IN (SELECT file_id FROM FileRegistry WHERE file_id IS NOT NULL)
            LIMIT 20
        """
        query_gaps_single = """
            SELECT DISTINCT 
                json_extract(p.content, '$.file_id') as fid, 
                json_extract(p.content, '$.type') as ftype,
                NULL as thumb_id,
                COALESCE(json_extract(p.content, '$.file_name'), json_extract(p.content, '$.filename')) as fname,
                json_extract(p.content, '$.mime_type') as fmime
            FROM Posts p
            WHERE p.post_num > (SELECT COALESCE(MAX(post_num), 0) - 250 FROM Posts)
              AND ftype IN ('image', 'photo', 'video', 'animation', 'gif', 'video_note', 'sticker', 'document')
              AND fid IS NOT NULL
              AND fid NOT IN (SELECT file_id FROM FileRegistry WHERE file_id IS NOT NULL)
            LIMIT 20
        """
        async def _fetch_gaps():
            gap_tasks = []
            async with db.execute(query_gaps_files) as cursor:
                async for row in cursor:
                    if row[0] and (not exclude_list or row[0] not in exclude_list) and not any(t["fid"] == row[0] for t in tasks):
                        gap_tasks.append(
                            {
                                "fid": row[0],
                                "type": row[1] or "photo",
                                "thumb_id": row[2],
                                "fname": row[3],
                                "fmime": row[4],
                                "bot_id": None,
                            }
                        )
            async with db.execute(query_gaps_single) as cursor:
                async for row in cursor:
                    if row[0] and (not exclude_list or row[0] not in exclude_list) and not any(t["fid"] == row[0] for t in tasks) and not any(g["fid"] == row[0] for g in gap_tasks):
                        gap_tasks.append(
                            {
                                "fid": row[0],
                                "type": row[1] or "photo",
                                "thumb_id": row[2],
                                "fname": row[3],
                                "fmime": row[4],
                                "bot_id": None,
                            }
                        )
            return gap_tasks

        try:
            gap_items = await execute_with_retry(_fetch_gaps, max_retries=3, base_delay=0.1)
            tasks.extend(gap_items)
        except Exception as e:
            logger.error(f"Gaps query error: {e}", exc_info=True)

    tasks = tasks[:BATCH_SIZE]

    # 3. Populate bot_id for the tasks
    if tasks:
        fids = [t["fid"] for t in tasks]
        placeholders = ",".join(["?"] * len(fids))
        async def _fetch_owners():
            owners_map = {}
            query_owners = f"SELECT file_id, bot_id FROM FileOwners WHERE file_id IN ({placeholders})"
            async with db.execute(query_owners, fids) as cursor:
                async for row in cursor:
                    owners_map[row[0]] = row[1]
            for t in tasks:
                t["bot_id"] = owners_map.get(t["fid"])

        try:
            await execute_with_retry(_fetch_owners, max_retries=3, base_delay=0.1)
        except Exception as e:
            logger.error(f"DB Error getting file owners: {e}", exc_info=True)

    return tasks


def _build_download_candidates(primary_bot) -> list:
    """Порядок ботов для попытки скачивания с учётом кулдаунов и доступности."""
    if global_bot_pool and hasattr(global_bot_pool, "get_download_candidates"):
        return global_bot_pool.get_download_candidates(primary_bot=primary_bot)

    bots_to_try = []
    if primary_bot:
        bots_to_try.append(primary_bot)

    main_bot = global_bot_pool.get_main_bot() if global_bot_pool else None
    if main_bot and main_bot not in bots_to_try:
        bots_to_try.append(main_bot)
    all_bots = []
    if global_bot_pool:
        if hasattr(global_bot_pool, "get_all_active_bots"):
            all_bots = global_bot_pool.get_all_active_bots(prioritize_ready=True)
        elif hasattr(global_bot_pool, "all_bots"):
            all_bots = global_bot_pool.all_bots
    for b in all_bots:
        if b not in bots_to_try:
            bots_to_try.append(b)
    return bots_to_try


async def _download_via_bot(bot, file_id: str) -> tuple[bytes | None, str]:
    """
    Одна попытка скачивания конкретным ботом под раздельными таймаутами.
    Возвращает (байты, статус): status in ('ok', 'not_found', 'file_too_big', 'no_file_path', 'empty')
    """
    f_info = await asyncio.wait_for(
        bot.get_file(file_id), timeout=GET_FILE_TIMEOUT_PER_BOT
    )
    file_size = getattr(f_info, "file_size", 0) or 0
    if file_size > MAX_FILE_SIZE_BOT_API:
        logger.debug(f"File {file_id[:15]} is {file_size} bytes (>20MB Bot API limit).")
        return None, "file_too_big"

    file_path = getattr(f_info, "file_path", None)
    if not file_path:
        return None, "no_file_path"

    f_obj = await asyncio.wait_for(
        bot.download_file(file_path), timeout=DOWNLOAD_DATA_TIMEOUT_PER_BOT
    )
    data = f_obj.read() if hasattr(f_obj, "read") else f_obj
    return (data, "ok") if data else (None, "empty")


async def download_file_with_fallback(file_id: str, primary_bot=None) -> tuple[bytes | None, any, str]:
    """
    Пробует скачать файл доступными ботами с быстрой ротацией и защитой от зависания.
    Возвращает: (img_bytes, active_bot, status)
    status: 'ok', 'not_found', 'file_too_big', 'timeout', 'failed'
    """
    if not file_id:
        return None, None, "failed"

    # Если file_id это прямой HTTP URL
    if str(file_id).startswith(("http://", "https://")):
        try:
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
                resp = await client.get(file_id)
                if resp.status_code == 200 and resp.content:
                    return resp.content, None, "ok"
        except Exception as http_err:
            logger.debug(f"Direct HTTP DL failed for {file_id[:15]}: {http_err}")

    bots_to_try = _build_download_candidates(primary_bot)
    if not bots_to_try:
        return None, None, "failed"

    deadline = time.monotonic() + DOWNLOAD_TOTAL_TIMEOUT
    all_not_found = True
    is_too_big = False
    timed_out_count = 0

    for b in bots_to_try:
        if time.monotonic() >= deadline:
            logger.warning(
                f"⏱️ [TAGGER] Общий бюджет скачивания исчерпан ({DOWNLOAD_TOTAL_TIMEOUT:.0f}s) для {file_id[:15]}."
            )
            break

        b_id = getattr(b, "id", None)
        try:
            img_bytes, status = await _download_via_bot(b, file_id)
            if status == "file_too_big":
                is_too_big = True
                all_not_found = False
                # Файл больше 20MB — никакой бот не сможет скачать его через Bot API
                break
            if img_bytes:
                return img_bytes, b, "ok"
        except asyncio.TimeoutError:
            all_not_found = False
            timed_out_count += 1
            logger.warning(
                f"⏱️ [TAGGER] Таймаут скачивания {file_id[:15]} ботом {b_id or '?'}, пробую следующего бота."
            )
            if global_bot_pool:
                global_bot_pool.mark_bot_cooldown_by_bot(b, duration_sec=30.0)
            continue
        except asyncio.CancelledError:
            raise
        except TelegramRetryAfter as e:
            all_not_found = False
            retry_secs = max(15.0, getattr(e, "retry_after", 15.0) or 15.0)
            logger.warning(f"⏳ [TAGGER] Bot {b_id or '?'} FloodWait {retry_secs}s.")
            if global_bot_pool:
                global_bot_pool.mark_bot_cooldown_by_bot(b, duration_sec=retry_secs)
            continue
        except (TelegramForbiddenError, TelegramUnauthorizedError) as e:
            all_not_found = False
            logger.error(f"🚨 [TAGGER] Bot {b_id or '?'} unauthorized/logged out: {e}")
            if global_bot_pool and hasattr(b, "token"):
                global_bot_pool.mark_bot_dead_by_token(b.token)
            continue
        except TelegramBadRequest as e:
            err_msg = str(e).lower()
            if "too big" in err_msg or "file is too big" in err_msg:
                is_too_big = True
                all_not_found = False
                break
            if "file is not found" in err_msg or "wrong file identifier" in err_msg or "invalid file_id" in err_msg:
                logger.debug(f"TelegramBadRequest for {file_id[:15]} on bot {b_id}: {e}")
                continue
            all_not_found = False
            logger.debug(f"TelegramBadRequest for {file_id[:15]} on bot {b_id}: {e}")
            continue
        except Exception as e:
            all_not_found = False
            err_str = str(e).lower()
            logger.warning(f"⚠️ [TAGGER] Ошибка при скачивании {file_id[:15]} ботом {b_id or '?'}: {repr(e)}")
            if (
                "logged out" in err_str
                or "unauthorized" in err_str
                or "token is invalid" in err_str
            ):
                if global_bot_pool and hasattr(b, "token"):
                    global_bot_pool.mark_bot_dead_by_token(b.token)
            elif "timeout" in err_str or "timed out" in err_str:
                if global_bot_pool:
                    global_bot_pool.mark_bot_cooldown_by_bot(b, duration_sec=30.0)
            continue

    # Если через Bot API не получилось, проверяем внешние зеркала (Catbox, Pixhost, etc.)
    try:
        from common.database import get_file_mirrors
        mirrors = await get_file_mirrors(file_id)
        if mirrors and isinstance(mirrors, dict):
            for m_type in ['catbox', 'pixhost', 'huggingface', '0x0', 'imgbb']:
                m_url = mirrors.get(m_type)
                if m_url and isinstance(m_url, str) and m_url.startswith(("http://", "https://")):
                    try:
                        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as http_c:
                            resp = await http_c.get(m_url)
                            if resp.status_code == 200 and resp.content:
                                logger.info(f"🌐 [TAGGER] Recovered media {file_id[:15]} from mirror {m_type}")
                                return resp.content, None, "ok"
                    except Exception:
                        continue
    except Exception:
        pass

    if is_too_big:
        return None, None, "file_too_big"
    if all_not_found:
        return None, None, "not_found"
    if timed_out_count > 0:
        return None, None, "timeout"
    return None, None, "failed"


# ==========================================
# ОСНОВНОЙ ЦИКЛ
# ==========================================
async def tagging_loop():
    logger.info("🚀 Tagging Worker Started (Single-Threaded + Resizer)")
    await asyncio.sleep(5)

    global TEMP_FAILED_FILES
    if TEMP_FAILED_FILES is None:
        TEMP_FAILED_FILES = {}

    # Считаем бэклог при старте
    try:
        db = await get_pool()
        async def _init_audio_tags():
            async with db_transaction(db):
                await db.execute(
                    "UPDATE FileRegistry SET tags='audio' WHERE file_type IN ('audio', 'voice') AND (tags IS NULL OR tags = '')"
                )
        await execute_with_retry(_init_audio_tags, max_retries=3, base_delay=0.2)

        async def _count_backlog():
            async with db.execute(
                "SELECT COUNT(*) FROM FileRegistry WHERE file_type IN ('image', 'photo') AND (tags IS NULL OR tags = '' OR phash IS NULL)"
            ) as cursor:
                return (await cursor.fetchone())[0]

        total_backlog = await execute_with_retry(_count_backlog, max_retries=3, base_delay=0.2)
        logger.info(f"📊 GLOBAL STATUS: {total_backlog} files waiting.")
    except Exception as e:
        logger.warning(f"Failed to query tagging backlog: {e}")

    loop = asyncio.get_running_loop()

    while True:
        try:
            now = time.time()
            if TEMP_FAILED_FILES:
                # Clean up entries older than 2 hours to avoid memory leaks, 
                # but preserve them long enough for retries
                TEMP_FAILED_FILES = {
                    k: v
                    for k, v in TEMP_FAILED_FILES.items()
                    if (v.get("until", 0) if isinstance(v, dict) else v) > now - 7200
                }

            # Собираем file_id на кулдауне, чтобы get_tasks не циклился на одних и тех же 50 элементах
            active_failed_fids = {
                k for k, v in TEMP_FAILED_FILES.items()
                if (v.get("until", 0) if isinstance(v, dict) else v) > now
            }

            db = await get_pool()
            if not db:
                await asyncio.sleep(5)
                continue

            # Забираем задачи с исключением находящихся на кулдауне
            all_tasks = await get_tasks(db, exclude_fids=active_failed_fids)

            # Фильтруем "временно упавшие"
            valid_task = None
            for t in all_tasks:
                failed_info = TEMP_FAILED_FILES.get(t["fid"])
                if not failed_info or (isinstance(failed_info, dict) and failed_info.get("until", 0) <= now):
                    valid_task = t
                    break

            if not valid_task:
                await asyncio.sleep(2)
                continue

            file_id = valid_task["fid"]
            bot_id = valid_task["bot_id"]
            file_type = valid_task["type"]
            thumb_id = valid_task.get("thumb_id")

            # 0. Fast-track для аудио (не требует скачивания тяжелых файлов через Bot API)
            is_audio = (
                file_type in ("audio", "voice")
                or is_audio_media(
                    file_type=file_type,
                    mime_type=valid_task.get("fmime"),
                    filename=valid_task.get("fname"),
                )
            )
            if is_audio:
                logger.info(
                    f"🎵 [BG_TAGGER] Audio task {file_id[:12]} (name={valid_task.get('fname')}, mime={valid_task.get('fmime')}) -> marked as 'audio' without Vision"
                )
                sha_audio = f"audio_{file_id}"
                async def _save_audio_fast():
                    async with db_transaction(db):
                        async with db.execute(
                            "SELECT sha256 FROM FileRegistry WHERE file_id=?",
                            (file_id,),
                        ) as cursor:
                            row = await cursor.fetchone()
                        if row:
                            await db.execute(
                                "UPDATE FileRegistry SET tags='audio', file_type='audio' WHERE file_id=?",
                                (file_id,),
                            )
                        else:
                            await db.execute(
                                "INSERT OR REPLACE INTO FileRegistry (sha256, file_id, thumbnail_id, file_type, tags, created_at) VALUES (?, ?, ?, 'audio', 'audio', ?)",
                                (sha_audio, file_id, thumb_id, time.time()),
                            )

                await execute_with_retry(_save_audio_fast, max_retries=5, base_delay=0.1)
                if file_id in TEMP_FAILED_FILES:
                    del TEMP_FAILED_FILES[file_id]
                await asyncio.sleep(0.1)
                continue

            bot = (
                global_bot_pool.get_bot_by_id(bot_id)
                if bot_id and global_bot_pool
                else (global_bot_pool.get_main_bot() if global_bot_pool else None)
            )

            # Определяем, что качать (для видео предпочтительно превью, иначе сам файл)
            download_target_id = (
                thumb_id
                if (
                    thumb_id
                    and file_type in {"video", "animation", "gif", "video_note"}
                )
                else file_id
            )

            try:
                # 1. СКАЧИВАНИЕ С РЕТРАЕМ ПО ВСЕМ БОТАМ
                img_bytes, active_bot, dl_status = await download_file_with_fallback(
                    download_target_id, primary_bot=bot
                )

                # Если превью не удалось скачать для видео, пробуем скачать сам файл видео (если не слишком большой)
                if not img_bytes and download_target_id != file_id and dl_status not in ("file_too_big",):
                    download_target_id = file_id
                    img_bytes, active_bot, dl_status = await download_file_with_fallback(
                        download_target_id, primary_bot=bot
                    )

                if not img_bytes:
                    entry = TEMP_FAILED_FILES.get(file_id)
                    fail_cnt = (
                        (entry.get("cnt", 0) + 1) if isinstance(entry, dict) else 1
                    )
                    # Если файл перманентно не найден ни одним ботом или слишком большой (>20MB),
                    # не мучаем очередь повторами — сразу помечаем download_failed
                    is_permanent_fail = dl_status in ("not_found", "file_too_big") or fail_cnt >= 3
                    
                    if is_permanent_fail:
                        reason_msg = f"status='{dl_status}'" if dl_status in ("not_found", "file_too_big") else f"failed {fail_cnt} times"
                        logger.warning(
                            f"⛔ [TAGGER] DL failed ({reason_msg}) for {file_id[:15]} across all bots. Marking as 'download_failed'."
                        )
                        async def _save_dl_failed():
                            async with db_transaction(db):
                                async with db.execute(
                                    "SELECT sha256 FROM FileRegistry WHERE file_id=?",
                                    (file_id,),
                                ) as cursor:
                                    row = await cursor.fetchone()
                                if row:
                                    await db.execute(
                                        "UPDATE FileRegistry SET tags='download_failed' WHERE file_id=?",
                                        (file_id,),
                                    )
                                else:
                                    dummy_sha = f"failed_{file_id}"
                                    await db.execute(
                                        "INSERT OR REPLACE INTO FileRegistry (sha256, file_id, thumbnail_id, file_type, tags, created_at) VALUES (?, ?, ?, ?, 'download_failed', ?)",
                                        (dummy_sha, file_id, thumb_id, file_type, time.time()),
                                    )

                        await execute_with_retry(_save_dl_failed, max_retries=5, base_delay=0.1)
                        if file_id in TEMP_FAILED_FILES:
                            del TEMP_FAILED_FILES[file_id]
                    else:
                        logger.debug(
                            f"❌ DL skip for {file_id[:15]} across bots (attempt {fail_cnt}/3, status={dl_status}). Retrying later."
                        )
                        TEMP_FAILED_FILES[file_id] = {
                            "until": time.time() + 180,
                            "cnt": fail_cnt,
                        }
                    continue

                # 2. CPU (Хеши + РЕСАЙЗ)
                res, error_msg = await loop.run_in_executor(
                    None, process_image_cpu, img_bytes
                )

                if error_msg == "audio_media" or is_audio_media(file_type=file_type, mime_type=valid_task.get("fmime"), filename=valid_task.get("fname"), data=img_bytes):
                    logger.info(
                        f"🎵 [BG_TAGGER] Audio document {file_id[:12]} (name={valid_task.get('fname')}, mime={valid_task.get('fmime')}) -> marked as 'audio' without Vision"
                    )
                    sha_audio = hashlib.sha256(img_bytes).hexdigest() if img_bytes else f"audio_{file_id}"
                    async def _save_audio_doc():
                        async with db_transaction(db):
                            async with db.execute(
                                "SELECT sha256 FROM FileRegistry WHERE file_id=?",
                                (file_id,),
                            ) as cursor:
                                row = await cursor.fetchone()
                            if row:
                                await db.execute(
                                    "UPDATE FileRegistry SET tags='audio', file_type='audio' WHERE file_id=?",
                                    (file_id,),
                                )
                            else:
                                await db.execute(
                                    "INSERT OR REPLACE INTO FileRegistry (sha256, file_id, thumbnail_id, file_type, tags, created_at) VALUES (?, ?, ?, 'audio', 'audio', ?)",
                                    (sha_audio, file_id, thumb_id, time.time()),
                                )

                    await execute_with_retry(_save_audio_doc, max_retries=5, base_delay=0.1)
                    if file_id in TEMP_FAILED_FILES:
                        del TEMP_FAILED_FILES[file_id]
                    continue

                if error_msg == "lottie_sticker":
                    logger.info(
                        f"🎨 [BG_TAGGER] Lottie Sticker {file_id[:12]} -> marked as 'sticker_animated'"
                    )
                    async def _save_lottie():
                        async with db_transaction(db):
                            async with db.execute(
                                "SELECT sha256 FROM FileRegistry WHERE file_id=?",
                                (file_id,),
                            ) as cursor:
                                row = await cursor.fetchone()
                            if row:
                                await db.execute(
                                    "UPDATE FileRegistry SET tags='sticker_animated' WHERE file_id=?",
                                    (file_id,),
                                )
                            else:
                                dummy_sha = f"sticker_{file_id}"
                                await db.execute(
                                    "INSERT OR REPLACE INTO FileRegistry (sha256, file_id, thumbnail_id, file_type, tags, created_at) VALUES (?, ?, ?, ?, 'sticker_animated', ?)",
                                    (dummy_sha, file_id, thumb_id, file_type, time.time()),
                                )

                    await execute_with_retry(_save_lottie, max_retries=5, base_delay=0.1)
                    continue
                elif error_msg and "unsupported_format" in error_msg:
                    logger.info(
                        f"📁 [BG_TAGGER] Media {file_id[:12]} -> marked as 'format_unsupported'"
                    )
                    async def _save_unsupported():
                        async with db_transaction(db):
                            async with db.execute(
                                "SELECT sha256 FROM FileRegistry WHERE file_id=?",
                                (file_id,),
                            ) as cursor:
                                row = await cursor.fetchone()
                            if row:
                                await db.execute(
                                    "UPDATE FileRegistry SET tags='format_unsupported' WHERE file_id=?",
                                    (file_id,),
                                )
                            else:
                                dummy_sha = f"unsupported_{file_id}"
                                await db.execute(
                                    "INSERT OR REPLACE INTO FileRegistry (sha256, file_id, thumbnail_id, file_type, tags, created_at) VALUES (?, ?, ?, ?, 'format_unsupported', ?)",
                                    (dummy_sha, file_id, thumb_id, file_type, time.time()),
                                )

                    await execute_with_retry(_save_unsupported, max_retries=5, base_delay=0.1)
                    continue
                elif not res:
                    logger.error(f"⚠️ Bad File {file_id}: {error_msg}")
                    # Сохраняем как ошибку, чтобы не долбить
                    sha_fail = hashlib.sha256(img_bytes).hexdigest()
                    async def _save_bad_file():
                        async with db_transaction(db):
                            await db.execute(
                                "UPDATE FileRegistry SET tags='error' WHERE file_id=?",
                                (file_id,),
                            )
                            await db.execute(
                                "INSERT OR IGNORE INTO FileRegistry (sha256, file_id, tags, created_at) VALUES (?, ?, 'error', ?)",
                                (sha_fail, file_id, time.time()),
                            )

                    await execute_with_retry(_save_bad_file, max_retries=5, base_delay=0.1)
                    continue

                sha, phash, b_hash, resized_bytes = res
                tags = None
                async def _check_existing_tags():
                    async with db.execute(
                        "SELECT tags FROM FileRegistry WHERE sha256 = ? AND tags IS NOT NULL AND tags != '' LIMIT 1",
                        (sha,),
                    ) as cursor:
                        return await cursor.fetchone()

                try:
                    row = await execute_with_retry(_check_existing_tags, max_retries=3, base_delay=0.1)
                    if row:
                        tags = row[0]
                        logger.info(f"♻️ Skip Neuro: Tags found for SHA {sha[:8]}")
                except Exception as e:
                    logger.error(
                        f"DB Error checking existing tags for SHA {sha[:8]}: {e}",
                        exc_info=True,
                    )

                # 3. НЕЙРОНКА (Только если теги еще не найдены в БД)
                description = None
                if tags is None:
                    ai_response = await get_neuro_tags(resized_bytes)
                    if ai_response in ("error_413", "error_too_large"):
                        tags = "error_too_large"
                    elif ai_response == "error_api_exhausted":
                        tags = None  # Force retry
                    elif ai_response == "error_file_invalid":
                        tags = "error_no_tags"  # Permanent failure
                    elif ai_response and ai_response.startswith("{"):
                        import json
                        try:
                            parsed = json.loads(ai_response)
                            raw_t = parsed.get("tags", "")
                            if isinstance(raw_t, list):
                                tags = ", ".join(str(t).strip() for t in raw_t if t)
                            else:
                                tags = str(raw_t or "").strip()
                            if tags == "parse_error":
                                tags = "media, photo"
                            description = str(parsed.get("description", "")).strip()
                        except json.JSONDecodeError:
                            tags = ai_response
                if tags is None and ai_response in (None, "error_api_exhausted"):
                    entry = TEMP_FAILED_FILES.get(file_id)
                    fail_cnt = ((entry.get("cnt", 0) + 1) if isinstance(entry, dict) else 1)
                    if fail_cnt >= 3:
                        logger.warning(f"⚠️ [TAGGER] AI tagging failed {fail_cnt} times for {file_id[:15]}. Saving visual hashes and marking as 'no_tags'.")
                        tags = "no_tags"
                        if file_id in TEMP_FAILED_FILES:
                            del TEMP_FAILED_FILES[file_id]
                    else:
                        cooldown_secs = 45 if ai_response == "error_api_exhausted" else 10
                        logger.warning(f"⏸️ [TAGGER] API exhausted or internal error (attempt {fail_cnt}/3 for {file_id[:15]}). Pausing tagger for {cooldown_secs}s cooldown before next file. Skipping DB update to retry later.")
                        TEMP_FAILED_FILES[file_id] = {
                            "until": time.time() + 300,
                            "cnt": fail_cnt,
                        }
                        await asyncio.sleep(cooldown_secs)
                        continue


                tag_mark = "🏷️" if (tags and "error" not in tags) else "⚪"

                save_success = False
                has_suspicious = False  # <--- ИНИЦИАЛИЗАЦИЯ

                async def _save_tags_registry():
                    async with db_transaction(db):
                        async with db.execute(
                            """
                            UPDATE FileRegistry 
                            SET tags = ?, description = COALESCE(?, description), phash = ?, blurhash = ?
                            WHERE file_id = ?
                        """,
                            (tags, description, phash, b_hash, file_id),
                        ) as cursor:
                            updated_rows = cursor.rowcount

                        if updated_rows == 0:
                            await db.execute(
                                """
                                INSERT INTO FileRegistry 
                                (sha256, phash, file_id, thumbnail_id, file_type, created_at, blurhash, tags, description)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                ON CONFLICT(sha256) DO UPDATE SET
                                    tags = excluded.tags,
                                    description = COALESCE(excluded.description, FileRegistry.description),
                                    phash = excluded.phash
                            """,
                                (
                                    sha,
                                    phash,
                                    file_id,
                                    None,
                                    file_type,
                                    time.time(),
                                    b_hash,
                                    tags,
                                    description,
                                ),
                            )

                try:
                    await execute_with_retry(_save_tags_registry, max_retries=5, base_delay=0.1)
                    save_success = True
                    logger.info(
                        f"🖼 [BG_TAGGER] ✅ {(file_type or 'media').upper()} {file_id[:12]} | {tag_mark} | Tags: '{tags[:200] if tags else 'none'}...'"
                    )
                except Exception as e:
                    logger.error(
                        f"❌ [BG_TAGGER] DB Save error for {file_id[:12]}: {e}",
                        exc_info=True,
                    )

                # === МОДЕРАЦИЯ (Deep Check) ===
                should_deep_check = False

                # Проверка исключительно по ключевым словам в тегах и описании с контролем границ слов
                if save_success and tags and "error" not in tags:
                    full_text = f"{tags} {description or ''}".lower()
                    # Исключаем ложные срабатывания (например, вейп charon_baby)
                    cleaned_text = re.sub(r'\bcharon[_\s]*baby\b', '', full_text)
                    
                    # Проверяем строго границы слов, чтобы не триггерить подстроки (kid в skid, baby в charon_baby и т.д.)
                    has_suspicious = any(
                        re.search(r'\b' + re.escape(w).replace(r'\ ', r'[\s_]+') + r'\b', cleaned_text)
                        for w in SUSPICIOUS_KEYWORDS
                    )
                    is_safe_style = any(s in full_text for s in SAFE_KEYWORDS)

                    # Чекаем только если есть подозрительные слова И ЭТО НЕ безопасный стиль (аниме/арт)
                    if has_suspicious and not is_safe_style:
                        should_deep_check = True

                if should_deep_check:
                    logger.warning(f"🛡️ Triggered DEEP CHECK for {file_id}")
                    spawn_task(run_deep_check(resized_bytes, file_id))

                if not tags:
                    entry = TEMP_FAILED_FILES.get(file_id)
                    fail_cnt = (entry.get("cnt", 0) + 1) if isinstance(entry, dict) else 1
                    if fail_cnt >= 5:
                        logger.warning(f"⛔ [TAGGER] No tags 5 times for {file_id[:15]}. Marking as 'error_no_tags'.")
                        async def _save_no_tags():
                            async with db_transaction(db):
                                await db.execute("UPDATE FileRegistry SET tags='error_no_tags' WHERE file_id=?", (file_id,))

                        try:
                            await execute_with_retry(_save_no_tags, max_retries=5, base_delay=0.1)
                        except Exception as e:
                            logger.error(f"DB Error saving error_no_tags: {e}")
                        if file_id in TEMP_FAILED_FILES:
                            del TEMP_FAILED_FILES[file_id]
                    else:
                        TEMP_FAILED_FILES[file_id] = {"until": time.time() + 60, "cnt": fail_cnt}

            except Exception as e:
                logger.error(f"💥 Crit fail {file_id}: {e}", exc_info=True)
                entry = TEMP_FAILED_FILES.get(file_id)
                fail_cnt = (entry.get("cnt", 0) + 1) if isinstance(entry, dict) else 1
                if fail_cnt >= 3:
                    logger.warning(f"⛔ [TAGGER] Crit fail 3 times for {file_id[:15]}. Marking as 'error'.")
                    async def _save_crit_fail():
                        async with db_transaction(db):
                            await db.execute("UPDATE FileRegistry SET tags='error' WHERE file_id=?", (file_id,))

                    try:
                        await execute_with_retry(_save_crit_fail, max_retries=5, base_delay=0.1)
                    except Exception as db_err:
                        logger.error(f"DB Error saving crit error: {db_err}")
                    if file_id in TEMP_FAILED_FILES:
                        del TEMP_FAILED_FILES[file_id]
                else:
                    TEMP_FAILED_FILES[file_id] = {"until": time.time() + 300, "cnt": fail_cnt}

            # Пауза между файлами (строго >= 2.5 сек для защиты API-ключей от спама)
            await asyncio.sleep(2.5)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.critical(f"Loop crash: {e}", exc_info=True)
            await asyncio.sleep(30)
