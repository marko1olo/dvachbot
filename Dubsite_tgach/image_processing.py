import asyncio
from common.task_manager import spawn_task
import logging
import re
import math
import imagehash
from io import BytesIO
from common.database import add_file_mirror, check_file_deduplication, register_new_file, check_phash_ban, add_to_hf_queue
from common.secret_redaction import install_logging_redaction
from site_tgach.catbox import upload_url_to_catbox, upload_bytes_to_catbox
from site_tgach.huggingface import upload_to_hf
from site_tgach.mtproto_client import upload_file_mtproto
from fastapi import UploadFile, HTTPException
from PIL import Image
from aiogram import Bot
from aiogram.types import BufferedInputFile
from common.board_config import SHADOW_CHANNEL_ID
from aiogram.exceptions import (
    TelegramRetryAfter, 
    TelegramNetworkError, 
    TelegramBadRequest
)
MIRROR_SEMAPHORE = asyncio.Semaphore(10) # Максимум 10 одновременных заливов
logging.basicConfig(level=logging.INFO)
install_logging_redaction()
logger = logging.getLogger("uploader")
THUMBNAIL_SIZE = (320, 320)
Image.MAX_IMAGE_PIXELS = 45_000_000
TELEGRAM_PHOTO_LIMIT = 10 * 1024 * 1024  # 10 MB
TELEGRAM_DOCUMENT_LIMIT = 50 * 1024 * 1024 # 50 MB
def clean_tags_string(text: str | None) -> str | None:
    if not text: return None
    cleaned = " ".join(text.split())
    cleaned = cleaned.replace(", ,", ",").replace(",,", ",")
    return cleaned
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
    if image.mode != "RGB": image = image.convert("RGB")
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
        max_val = 1.0
        hash_list.append(encode_83(0, 1))
    hash_list.append(encode_dc(dc))
    for factor in ac: hash_list.append(encode_ac(factor, max_val))
    return "".join(hash_list)
from concurrent.futures import ThreadPoolExecutor

_process_pool = None
_thumb_process_pool = None

MAX_PIXELS = 16_000_000

def _grimdark_worker(image_bytes: bytes) -> bytes:
    """
    Функция-воркер. Запускается в отдельном ПРОЦЕССЕ.
    """
    try:
        from PIL import Image, ImageEnhance, ImageFilter
        import random
        Image.MAX_IMAGE_PIXELS = MAX_PIXELS
        stream = BytesIO(image_bytes)
        with Image.open(stream) as img:
            width, height = img.size
            if width * height > MAX_PIXELS:
                return image_bytes

            if img.mode != 'RGB':
                img = img.convert('RGB')

            # Тяжелая обработка
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.2)
            enhancer = ImageEnhance.Color(img)
            img = enhancer.enhance(0.6)
            
            noise = Image.effect_noise((width, height), 15).convert('RGB')
            img = Image.blend(img, noise, 0.15)
            
            overlay_color = random.choice([(40, 10, 0), (10, 20, 10), (30, 0, 0)]) 
            overlay = Image.new('RGB', img.size, overlay_color)
            img = Image.blend(img, overlay, 0.2)
            img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))

            output = BytesIO()
            img.save(output, format='JPEG', quality=85)
            return output.getvalue()
    except Exception as e:
        print(f"⚠️ Grimdark process error: {e}")
        return image_bytes

async def apply_grimdark_filter_async(image_bytes: bytes) -> bytes:
    global _process_pool
    if _process_pool is None:
        _process_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="grimdark")
    """Асинхронная обертка для вызова в процессе"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_process_pool, _grimdark_worker, image_bytes)
async def process_and_upload_image(
    file: UploadFile, 
    max_size_bytes: int, 
    bot: Bot, 
    channel_id: int
) -> dict:
    import os
    import hashlib
    from common.bot_pool import global_bot_pool
    
    content_type = file.content_type
    original_filename = file.filename or "file"
    
    ALLOWED_EXTS = {
        '.jpg', '.jpeg', '.png', '.webp', '.gif', 
        '.mp4', '.webm', '.mov', '.mkv', 
        '.ogg', '.mp3', '.wav', '.opus'
    }
    ext = os.path.splitext(original_filename)[1].lower()
    
    if hasattr(file, 'size') and isinstance(file.size, int) and file.size > max_size_bytes:
         raise HTTPException(status_code=413, detail="File too large")
    
    try:
        await file.seek(0)
        contents = await file.read()
    except Exception:
        raise HTTPException(400, "Client disconnected during upload")
    
    if len(contents) > max_size_bytes:
        raise HTTPException(status_code=413, detail="File too large")
    
    HASH_LIMIT = 50 * 1024 * 1024
    is_image_mime = content_type.startswith("image/")
    sha256_hash = None
    dedup_result = None
    
    if is_image_mime or len(contents) <= HASH_LIMIT:
        loop = asyncio.get_running_loop()
        sha256_hash = await loop.run_in_executor(None, lambda: hashlib.sha256(contents).hexdigest())
        dedup_result = await check_file_deduplication(sha256_hash)
    
    if dedup_result:
        if dedup_result.get("banned"):
            return {"banned": True, "reason": "Banned by SHA256"}
        if dedup_result.get("found"):
            return {
                "type": dedup_result['type'],
                "original_file_id": dedup_result['original_file_id'],
                "thumbnail_file_id": dedup_result['thumbnail_file_id'],
                "filename": original_filename,
                "phash": dedup_result.get('phash'),
                "blurhash": dedup_result.get('blurhash'),
                "sha256": sha256_hash
            }

    clean_name = re.sub(r'[^a-zA-Z0-9._-]', '_', original_filename)
    clean_name = re.sub(r'_+', '_', clean_name).strip('_')
    name_part, ext_part = os.path.splitext(clean_name)
    if len(name_part) > 50: name_part = name_part[:50]
    filename = f"{name_part}{ext_part}"
    if not filename or filename == ext_part:
        filename = f"file_{int(time.time())}{ext_part}"

    file_type = "document"
    if content_type.startswith("image/") and content_type != "image/gif":
        file_type = "image"
    elif (content_type in ["video/mp4", "video/quicktime"] or filename.lower().endswith(('.mp4', '.mov', '.mkv'))) and not filename.lower().endswith('.webm'):
        file_type = "video"
    elif filename.lower().endswith('.webm'):
        file_type = "document"
    elif content_type == "image/gif" or filename.lower().endswith(".gif"):
        file_type = "gif"
    elif content_type.startswith("audio/") or content_type == "application/ogg":
        file_type = "audio"
    if content_type == "image/webp" or filename.lower().endswith(".webp"):
        file_type = "sticker"

    phash_str = None
    blurhash_str = None
    thumbnail_bytes = None
    is_image = file_type == "image"

    if is_image:
        try:
            thumbnail_bytes = await create_thumbnail_in_memory(contents)
            
            def _validate_and_phash():
                img = Image.open(BytesIO(contents))
                if img.format not in ['JPEG', 'PNG', 'WEBP']: return None
                return str(imagehash.phash(img))
            
            phash_str = await asyncio.to_thread(_validate_and_phash)
            if phash_str and await check_phash_ban(phash_str):
                return {"banned": True, "reason": "Banned by pHash"}
                
            if thumbnail_bytes:
                try:
                    def _calc_blur():
                        with Image.open(BytesIO(thumbnail_bytes)) as im:
                            small = im.resize((32, 32))
                            return encode_blurhash_internal(small, 4, 3)
                    blurhash_str = await asyncio.to_thread(_calc_blur)
                except: pass
        except Exception as e:
            logger.warning(f"Image processing error: {e}")

    last_error = None
    result_data = None

    for attempt_bot_idx in range(3):
        if attempt_bot_idx == 0:
            current_bot = bot
        else:
            try:
                _, current_bot = global_bot_pool.get_next_bot('ru')
            except: current_bot = bot
        
        current_bot_id = getattr(current_bot, 'id', 'unknown')
        
        async def _send_with_retry(method_name, input_file_obj, **kwargs):
            for attempt in range(1, 4): 
                try:
                    method = getattr(current_bot, method_name)
                    return await method(request_timeout=120, **kwargs)
                except TelegramRetryAfter as e:
                    await asyncio.sleep(e.retry_after + 1)
                except TelegramBadRequest as e:
                    if "DIMENSIONS" in str(e).upper() and method_name == "send_photo":
                        raise ValueError("FALLBACK_TO_DOC")
                    raise e 
                except (TelegramNetworkError, asyncio.TimeoutError):
                    if attempt == 3: raise
                    await asyncio.sleep(2)

        def get_fid(obj):
            """Универсальный поиск file_id в любом объекте или сообщении."""
            if not obj: return None
            if hasattr(obj, 'file_id'): return obj.file_id
            for attr in ['video', 'document', 'animation', 'sticker', 'audio', 'voice']:
                field = getattr(obj, attr, None)
                if field and hasattr(field, 'file_id'):
                    return field.file_id
            photo = getattr(obj, 'photo', None)
            if photo and isinstance(photo, list) and len(photo) > 0:
                return photo[-1].file_id
                
            return None

        try:
            input_file = BufferedInputFile(contents, filename=filename)
            result_file_id = None
            thumb_id = None
            final_type = file_type 

            if file_type == "image":
                try:
                    is_too_heavy_for_photo = len(contents) > 9 * 1024 * 1024 
                    
                    if not is_too_heavy_for_photo:
                        try:
                            sent_original = await _send_with_retry("send_photo", input_file, chat_id=channel_id, photo=input_file)
                            if sent_original and sent_original.photo:
                                result_file_id = get_fid(sent_original.photo[-1])
                                thumb_id = get_fid(sent_original.photo[0])
                        except ValueError: 
                            is_too_heavy_for_photo = True
                    
                    if is_too_heavy_for_photo or not result_file_id:
                        sent_original = await _send_with_retry("send_document", input_file, chat_id=channel_id, document=input_file)
                        if sent_original and sent_original.document:
                            result_file_id = get_fid(sent_original.document)
                            if sent_original.document.thumbnail:
                                thumb_id = get_fid(sent_original.document.thumbnail)
                        
                except Exception as e:
                    logger.error(f"Image sub-upload failed: {e}")
                    raise e
            
            elif file_type == "video":
                sent_msg = await _send_with_retry("send_video", input_file, chat_id=channel_id, video=input_file)
                result_file_id = get_fid(sent_msg)
                media_obj = getattr(sent_msg, 'video', None) or getattr(sent_msg, 'document', None) or getattr(sent_msg, 'animation', None)
                if media_obj and getattr(media_obj, 'thumbnail', None): 
                    thumb_id = get_fid(media_obj.thumbnail)
                final_type = "video"
            
            elif file_type == "gif":
                sent_msg = await _send_with_retry("send_animation", input_file, chat_id=channel_id, animation=input_file)
                result_file_id = get_fid(sent_msg)
                
                media_obj = getattr(sent_msg, 'animation', None) or getattr(sent_msg, 'document', None)
                if media_obj and getattr(media_obj, 'thumbnail', None): 
                    thumb_id = get_fid(media_obj.thumbnail)
                final_type = "animation"

            elif file_type == "audio":
                kw = "voice" if ("ogg" in content_type or "opus" in content_type) else "audio"
                method = "send_voice" if kw == "voice" else "send_audio"
                sent_msg = await _send_with_retry(method, input_file, chat_id=channel_id, **{kw: input_file})
                
                if kw == "voice":
                    voice_obj = getattr(sent_msg, 'voice', None)
                    result_file_id = get_fid(voice_obj)
                else:
                    audio_obj = getattr(sent_msg, 'audio', None)
                    result_file_id = get_fid(audio_obj)
                    if audio_obj and audio_obj.thumbnail: 
                        thumb_id = get_fid(audio_obj.thumbnail)
                final_type = kw

            elif file_type == "sticker":
                sent_msg = await _send_with_retry("send_sticker", input_file, chat_id=channel_id, sticker=input_file)
                result_file_id = get_fid(sent_msg.sticker)
                if sent_msg.sticker.thumbnail: thumb_id = get_fid(sent_msg.sticker.thumbnail)
                final_type = "sticker"

            else: 
                sent_msg = await _send_with_retry("send_document", input_file, chat_id=channel_id, document=input_file)
                result_file_id = get_fid(sent_msg.document)
                if sent_msg.document.thumbnail: thumb_id = get_fid(sent_msg.document.thumbnail)
                final_type = "document"

            if not result_file_id:
                logger.info(f"🔄 Bot API failed for {filename}. Trying MTProto Fallback...")
                mt_res = await upload_file_mtproto(current_bot.token, channel_id, contents, filename, file_type)
                if mt_res and mt_res.get('file_id'):
                    result_file_id = mt_res['file_id']
                    thumb_id = mt_res.get('thumb_id')
                    channel_msg_id = mt_res.get('message_id')
                else:
                    raise Exception(f"Both Bot API and MTProto failed for {filename}")
            else:
                channel_msg_id = None
                if 'sent_original' in locals():
                    channel_msg_id = sent_original.message_id
                elif 'sent_msg' in locals():
                    channel_msg_id = sent_msg.message_id

            result_data = {
                "type": final_type,
                "original_file_id": result_file_id,
                "thumbnail_file_id": thumb_id,
                "filename": filename,
                "phash": phash_str,
                "blurhash": blurhash_str,
                "sha256": sha256_hash,
                "channel_message_id": channel_msg_id
            }
            break

        except Exception as e:
            logger.error(f"Bot {current_bot_id} upload failed: {e}")
            last_error = e
            continue

    if not result_data:
        raise HTTPException(status_code=500, detail=f"Upload failed: {last_error}")

    try:
        await register_new_file(
            sha256_hash, 
            phash_str, 
            result_data['original_file_id'], 
            result_data['thumbnail_file_id'], 
            result_data['type'], 
            blurhash_str
        )
    except Exception as e:
        logger.error(f"DB Register error: {e}")

    spawn_task(_upload_mirrors_task(
        current_bot, 
        result_data['original_file_id'], 
        file_bytes=contents,
        filename=filename,
        related_id=result_data['thumbnail_file_id']
    ))
    

    return result_data
async def create_thumbnail_in_memory(image_bytes: bytes) -> bytes | None:
    global _thumb_process_pool
    if _thumb_process_pool is None:
        _thumb_process_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="thumb")
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_thumb_process_pool, _create_thumbnail_sync_in_memory, image_bytes)
def shutdown_image_executors():
    global _process_pool, _thumb_process_pool
    for executor in (_process_pool, _thumb_process_pool):
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)
    _process_pool = None
    _thumb_process_pool = None
def _create_thumbnail_sync_in_memory(image_bytes: bytes) -> bytes | None:
    try:
        with Image.open(BytesIO(image_bytes)) as img:
            img.thumbnail(THUMBNAIL_SIZE)
            buffer = BytesIO()
            if img.mode in ("RGBA", "P"): img = img.convert("RGB")
            img.save(buffer, format="JPEG", optimize=True, quality=85)
            buffer.seek(0)
            return buffer.getvalue()
    except Image.DecompressionBombError:
        logger.warning("💣 Detected Decompression Bomb attempt!")
        return None
    except Exception as e:
        return None
async def _upload_mirrors_task(bot: Bot, file_id: str, file_bytes: bytes, filename: str, related_id: str = None):
    # 1. Теневой канал (Shadow)
    try:
        if SHADOW_CHANNEL_ID:
            shadow_fid = None
            shadow_thumb_fid = None
            try:
                msg = None
                # Пробуем разные методы отправки
                methods = [
                    (bot.send_video, {'video': file_id}),
                    (bot.send_document, {'document': file_id}),
                    (bot.send_photo, {'photo': file_id}),
                    (bot.send_animation, {'animation': file_id})
                ]
                for method, kwargs in methods:
                    try:
                        msg = await method(chat_id=SHADOW_CHANNEL_ID, **kwargs)
                        if msg: break
                    except: continue

                if msg:
                    # Извлекаем ID из результата
                    if msg.video: 
                        shadow_fid = msg.video.file_id
                        if msg.video.thumbnail: shadow_thumb_fid = msg.video.thumbnail.file_id
                    elif msg.document: 
                        shadow_fid = msg.document.file_id
                        if msg.document.thumbnail: shadow_thumb_fid = msg.document.thumbnail.file_id
                    elif msg.photo: 
                        shadow_fid = msg.photo[-1].file_id
                    elif msg.animation: 
                        shadow_fid = msg.animation.file_id
                        if msg.animation.thumbnail: shadow_thumb_fid = msg.animation.thumbnail.file_id
            except Exception:
                pass

            if shadow_fid:
                await add_file_mirror(file_id, 'tg_shadow', shadow_fid)
            if related_id and shadow_thumb_fid:
                await add_file_mirror(related_id, 'tg_shadow', shadow_thumb_fid)
    except Exception as e:
        logger.error(f"Shadow task error: {e}")

    # 2. Логика зеркал (Catbox + HF)
    
    # Всегда добавляем превью в очередь HF, так как они маленькие
    if related_id:
        await add_to_hf_queue(related_id)

    # Если файл > 19MB, Telegram не отдаст ссылку. Грузим байты напрямую.
    SIZE_LIMIT = 19 * 1024 * 1024
    
    if len(file_bytes) > SIZE_LIMIT:
        logger.info(f"🐘 Large file ({len(file_bytes)//1024//1024}MB) detected. Using Direct Bytes Upload strategy.")
        
        # Запускаем параллельно, чтобы быстрее отдать результат
        async def _catbox_direct():
            link = await upload_bytes_to_catbox(file_bytes, filename)
            if link: await add_file_mirror(file_id, 'catbox', link)
            
        async def _hf_direct():
            link = await upload_to_hf(file_bytes, filename)
            if link: await add_file_mirror(file_id, 'huggingface', link)

        await asyncio.gather(_catbox_direct(), _hf_direct())
    
    else:
        # Файл маленький, идем по стандартному пути (очереди и ссылки)
        await add_to_hf_queue(file_id)
        
        try:
            file_info = await bot.get_file(file_id)
            file_path = getattr(file_info, "file_path", None)
            
            if file_path:
                tg_url = f"https://api.telegram.org/file/bot{bot.token}/{file_path}"
                catbox_link = await upload_url_to_catbox(tg_url)
            else:
                catbox_link = None

            if catbox_link:
                await add_file_mirror(file_id, 'catbox', catbox_link)
            else:
                from common.database import add_to_mirror_queue
                await add_to_mirror_queue(file_id, 'catbox')
                
        except Exception:
            # Если не удалось получить ссылку даже для мелкого файла
            from common.database import add_to_mirror_queue
            await add_to_mirror_queue(file_id, 'catbox')
