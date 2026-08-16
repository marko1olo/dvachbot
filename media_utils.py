import os
import asyncio
import io
import logging
import aiohttp
from PIL import Image
from typing import Optional, Tuple
from japanese_translator import get_dynamic_proxy_url

logger = logging.getLogger(__name__)


async def _download_image_with_proxy(url: str, timeout: int=90, depth: int=0) -> tuple[bytes, int] | None:
    if depth > 3:
        return None
    import socket
    import ssl
    import aiohttp
    import asyncio
    import hashlib
    from urllib.parse import urlparse
    current_proxy = get_dynamic_proxy_url()
    timeout_config = aiohttp.ClientTimeout(total=timeout, connect=30, sock_connect=30, sock_read=timeout)
    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    scheme = parsed_url.scheme
    _, url_ext = os.path.splitext(parsed_url.path)
    url_log = f"host={domain or 'unknown'} ext={url_ext.lower()[:12] or 'none'} sha12={hashlib.sha256(url.encode('utf-8', 'ignore')).hexdigest()[:12]}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36', 'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8', 'Accept-Language': 'en-US,en;q=0.9', 'Accept-Encoding': 'gzip, deflate, br', 'Connection': 'keep-alive', 'Sec-Fetch-Dest': 'image', 'Sec-Fetch-Mode': 'no-cors', 'Sec-Fetch-Site': 'cross-site', 'Pragma': 'no-cache', 'Cache-Control': 'no-cache'}
    if 'gelbooru' in domain:
        headers['Referer'] = 'https://gelbooru.com/'
    elif 'konachan' in domain:
        headers['Referer'] = 'https://konachan.com/'
    elif 'yande.re' in domain:
        headers['Referer'] = 'https://yande.re/'
    elif 'danbooru' in domain:
        headers['Referer'] = 'https://danbooru.donmai.us/'
    elif 'aibooru' in domain:
        headers['Referer'] = 'https://aibooru.online/'
    elif 'safebooru' in domain:
        headers['Referer'] = 'https://safebooru.org/'
    elif 'nekobot' in domain:
        headers['Referer'] = 'https://nekobot.xyz/'
    elif '4cdn' in domain or '4chan' in domain:
        headers['Referer'] = 'https://boards.4channel.org/'
    elif 'pic.re' in domain:
        headers['Referer'] = 'https://pic.re/'
    else:
        headers['Referer'] = f'{scheme}://{domain}/'
    for attempt in range(2):
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        connector = aiohttp.TCPConnector(family=socket.AF_INET, ssl=ssl_context, force_close=True, enable_cleanup_closed=True)
        try:
            async with aiohttp.ClientSession(timeout=timeout_config, headers=headers, connector=connector, trust_env=False) as session:
                try:
                    async with session.get(url, allow_redirects=True, proxy=current_proxy) as response:
                        if response.status == 200:
                            content_type = response.headers.get('Content-Type', '').lower()
                            data = await response.read()
                            if 'text/html' in content_type or (len(data) > 0 and data.strip().startswith(b'<') and (b'<html' in data[:500].lower())):
                                try:
                                    error_text = data[:300].decode('utf-8', errors='ignore').replace('\n', ' ')
                                except Exception:
                                    error_text = 'Binary/Unknown'
                                print(f'⚠️ [DEBUG_DL] Ссылка вернула HTML заглушку. Содержимое: {error_text}')
                                return None
                            if len(data) > 49.5 * 1024 * 1024:
                                logger.debug(f'⚠️ [DEBUG_DL] Файл слишком велик ({len(data)} байт). Пропуск.')
                                return None
                            if len(data) > 0:
                                logger.debug(f'✅ [DEBUG_DL] Скачано {len(data)} байт.')
                                return (data, len(data))
                        else:
                            logger.debug(f'⚠️ [DEBUG_DL] Статус ответа: {response.status} для {url_log}')
                except (aiohttp.ClientConnectorError, asyncio.TimeoutError, OSError) as e:
                    if current_proxy:
                        logger.debug(f'⚠️ [DEBUG_DL] Сбой прокси ({e}). Пробую DIRECT...')
                        async with session.get(url, allow_redirects=True, proxy=None) as response:
                            if response.status == 200:
                                data = await response.read()
                                if len(data) > 0 and (not (data.strip().startswith(b'<') and b'<html' in data[:200].lower())):
                                    logger.debug(f'✅ [DEBUG_DL] Успех через DIRECT.')
                                    return (data, len(data))
                    raise e
        except asyncio.TimeoutError:
            if attempt == 0:
                await asyncio.sleep(1)
                continue
            else:
                logger.debug(f'⛔ [DEBUG_DL] Таймаут соединения.')
        except Exception as e:
            logger.debug(f'⛔ [DEBUG_DL] Исключение: {type(e).__name__}: {e}')
            break
    return None

def extract_msg_media_file_id(msg):
    if not msg: return None
    if getattr(msg, 'photo', None): return msg.photo[-1].file_id
    if getattr(msg, 'video', None):
        thumb = getattr(msg.video, 'thumbnail', None) or getattr(msg.video, 'thumb', None)
        return thumb.file_id if thumb else msg.video.file_id
    if getattr(msg, 'animation', None):
        thumb = getattr(msg.animation, 'thumbnail', None) or getattr(msg.animation, 'thumb', None)
        return thumb.file_id if thumb else msg.animation.file_id
    if getattr(msg, 'video_note', None):
        thumb = getattr(msg.video_note, 'thumbnail', None) or getattr(msg.video_note, 'thumb', None)
        return thumb.file_id if thumb else msg.video_note.file_id
    if getattr(msg, 'sticker', None): return msg.sticker.file_id
    if getattr(msg, 'document', None):
        thumb = getattr(msg.document, 'thumbnail', None) or getattr(msg.document, 'thumb', None)
        return thumb.file_id if thumb else msg.document.file_id
    return None

def _resize_image_if_needed(image_bytes: bytes) -> bytes:
    """
    (СИНХРОННАЯ) Оптимизированная проверка и ресайз.
    ВАЖНО: Пропускает видео (MP4, WebM) и анимированные GIF без изменений, чтобы не ломать кодировку.
    Корректно обрабатывает прозрачность RGBA/LA на белый фон без черных артефактов.
    """
    MAX_DIMENSION_SUM = 10000
    MAX_ASPECT_RATIO = 20.0
    MAX_FILE_SIZE_BYTES = 9.5 * 1024 * 1024
    if not image_bytes:
        return image_bytes
    header = image_bytes[:12]
    is_media_format = b'ftyp' in header or header.startswith(b'\x1aE\xdf\xa3') or header.startswith(b'GIF8')
    if is_media_format:
        return image_bytes
    try:
        input_size = len(image_bytes)
        with Image.open(io.BytesIO(image_bytes)) as img:
            width, height = img.size
            format_original = img.format
            if getattr(img, 'is_animated', False):
                return image_bytes
            needs_resize_dims = width + height > MAX_DIMENSION_SUM or width / height > MAX_ASPECT_RATIO or height / width > MAX_ASPECT_RATIO
            if not needs_resize_dims and input_size <= MAX_FILE_SIZE_BYTES:
                if format_original == 'PNG' and input_size > 5 * 1024 * 1024:
                    pass
                else:
                    return image_bytes

            # Корректная обработка прозрачности (белый фон вместо черного)
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                alpha_img = img.convert('RGBA')
                bg = Image.new('RGB', alpha_img.size, (255, 255, 255))
                bg.paste(alpha_img, mask=alpha_img.split()[3])
                img = bg
            else:
                img = img.convert('RGB')

            new_width, new_height = (width, height)
            if width + height > MAX_DIMENSION_SUM:
                scale_factor = MAX_DIMENSION_SUM / (width + height)
                new_width = int(width * scale_factor)
                new_height = int(height * scale_factor)
            if new_width / new_height > MAX_ASPECT_RATIO:
                new_width = int(new_height * MAX_ASPECT_RATIO)
            elif new_height / new_width > MAX_ASPECT_RATIO:
                new_height = int(new_width * MAX_ASPECT_RATIO)
            if new_width != width or new_height != height:
                img = img.resize((max(1, new_width), max(1, new_height)), Image.LANCZOS)
            quality = 95
            output_buffer = io.BytesIO()
            img.save(output_buffer, format='JPEG', quality=quality)
            current_size = output_buffer.tell()
            while current_size > MAX_FILE_SIZE_BYTES and quality > 10:
                output_buffer.seek(0)
                output_buffer.truncate(0)
                if quality < 60:
                    img = img.resize((int(img.width * 0.85), int(img.height * 0.85)), Image.LANCZOS)
                quality -= 10
                img.save(output_buffer, format='JPEG', quality=quality)
                current_size = output_buffer.tell()
            return output_buffer.getvalue()
    except Exception as e:
        return image_bytes