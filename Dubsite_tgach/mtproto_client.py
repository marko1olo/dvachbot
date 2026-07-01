import os
import logging
import asyncio
from common.task_manager import spawn_task
import time
import random
from pyrogram import Client
from pyrogram.errors import FileReferenceExpired
from dotenv import load_dotenv
from common.secret_redaction import secret_fingerprint

load_dotenv()

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")

logger = logging.getLogger("mtproto")
# Подавляем шумные ошибки Pyrogram (например, 400 Bad Request при протухших файлах)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

try:
    import tgcrypto
except ImportError:
    logger.warning("⚠️ TGCRYPTO NOT INSTALLED! Download speed will be very slow. Run: pip install tgcrypto")

# Глобальный кэш запущенных клиентов: {bot_token: Client}
_ACTIVE_CLIENTS = {}
_LAST_USED = {}  # {bot_token: timestamp}
_CLIENT_LOCK = asyncio.Lock()   
_CONNECTION_COOLDOWN = {}

_cleanup_in_progress = False

async def _cleanup_idle_clients():
    """Отключает клиенты, которые не использовались более 10 минут."""
    global _cleanup_in_progress
    if _cleanup_in_progress:
        return
    _cleanup_in_progress = True
    try:
        now = time.time()
        idle_timeout = 600 # 10 минут
        
        tokens_to_remove = []
        
        # Ищем кандидатов на удаление (без лока, чтобы не блокировать всё)
        for token, last_time in _LAST_USED.items():
            if now - last_time > idle_timeout:
                tokens_to_remove.append(token)
                
        if not tokens_to_remove:
            return

        async with _CLIENT_LOCK:
            for token in tokens_to_remove:
                client = _ACTIVE_CLIENTS.get(token)
                if client:
                    raw_cleanup_token = token
                    try:
                        if client.is_connected:
                            await client.stop()
                        token = secret_fingerprint(token)
                        logger.info(f"💤 [MTProto] Client stopped due to inactivity: {token[:10]}...")
                    except Exception as e:
                        logger.warning(f"⚠️ Error stopping idle client: {e}")
                    
                    token = raw_cleanup_token
                    _ACTIVE_CLIENTS.pop(token, None)
                    _LAST_USED.pop(token, None)
    finally:
        _cleanup_in_progress = False

async def get_active_client(bot_token: str):
    """
    Возвращает живой клиент Pyrogram с защитой от флуда и авто-очисткой.
    """
    # 0. Периодическая очистка (с вероятностью 5% при каждом вызове)
    if len(_ACTIVE_CLIENTS) > 5 and random.random() < 0.05:
        spawn_task(_cleanup_idle_clients())

    # 1. Проверка кулдауна
    if time.time() < _CONNECTION_COOLDOWN.get(bot_token, 0):
        return None

    async with _CLIENT_LOCK:
        _LAST_USED[bot_token] = time.time()
        
        if bot_token in _ACTIVE_CLIENTS:
            client = _ACTIVE_CLIENTS[bot_token]
            if client.is_connected:
                return client
            else:
                try: 
                    await client.start()
                    return client
                except Exception as e:
                    raw_bot_token = bot_token
                    bot_token = secret_fingerprint(bot_token)
                    logger.warning(f"⚠️ Reconnect failed for {bot_token[:10]}...: {e}")
                    bot_token = raw_bot_token
                    del _ACTIVE_CLIENTS[bot_token]

        short_token = secret_fingerprint(bot_token)
        
        client = Client(
            name=f"mem_session_{short_token}",
            api_id=int(API_ID),
            api_hash=API_HASH,
            bot_token=bot_token,
            no_updates=True, 
            in_memory=True,
            ipv6=False
        )

        try:
            await client.start()
            _ACTIVE_CLIENTS[bot_token] = client
            logger.info(f"🔌 [MTProto] Client started (In-Memory) for bot {short_token}")
            return client
        except Exception as e:
            logger.error(f"❌ Failed to start MTProto client: {e}")
            _CONNECTION_COOLDOWN[bot_token] = time.time() + 60
            return None

async def download_file_mtproto(bot_token: str, file_id: str, output_path: str, chat_id: int = None, message_id: int = None) -> bool:
    if not API_ID or not API_HASH:
        logger.error("API_ID/HASH missing in .env")
        return False

    out_dir = os.path.dirname(output_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    client = await get_active_client(bot_token)
    if not client:
        return False

    try:
        target = file_id
        if chat_id and message_id:
            try:
                msg = await client.get_messages(chat_id, message_id)
                if msg and not msg.empty:
                    target = msg
                else:
                    logger.warning(f"⚠️ [MTProto] Message {chat_id}/{message_id} not found. Skipping.")
                    return False
            except Exception:
                pass 

        # ИЗМЕНЕНИЕ: Жесткий тайм-аут 300 секунд (5 минут) на скачивание
        path = await asyncio.wait_for(
            client.download_media(
                message=target,
                file_name=output_path,
            ),
            timeout=300
        )
        
        if path and os.path.exists(output_path):
            return True
        else:
            return False
    
    except asyncio.TimeoutError:
        logger.error(f"❌ [MTProto] Download Timed Out (300s): {file_id[:15]}...")
        return False
    except FileReferenceExpired:
        logger.warning(f"⚠️ [MTProto] File reference expired for {file_id[:10]}...")
        return False
    except Exception as e:
        err_str = str(e)
        if "420" in err_str or "FLOOD_WAIT" in err_str:
            logger.critical(f"⛔ [MTProto] FLOOD WAIT DETECTED: {e}")
            _CONNECTION_COOLDOWN[bot_token] = time.time() + 300 # Бан на 5 минут
        elif "400" in err_str or "FILE_REFERENCE" in err_str:
             logger.warning(f"⚠️ [MTProto] Bad Request (dead file): {e}")
        elif "THUMBNAIL_SOURCE" in err_str.upper():
             logger.warning(f"⚠️ [MTProto] Pyrogram failed to parse thumb source for {file_id[:10]}")
        else:
            logger.error(f"❌ [MTProto] Download Error: {e}")
        return False

async def upload_file_mtproto(bot_token: str, chat_id: int, file_bytes: bytes, filename: str, file_type: str) -> dict | None:
    """Загружает файл через MTProto (Pyrogram) если Bot API не справляется."""
    client = await get_active_client(bot_token)
    if not client:
        return None

    import io
    file_io = io.BytesIO(file_bytes)
    file_io.name = filename

    try:
        msg = None
        if file_type == "photo" or filename.lower().endswith(('.jpg', '.jpeg', '.png')):
            msg = await client.send_photo(chat_id, file_io)
        elif file_type == "video" and filename.lower().endswith('.mp4'):
            msg = await client.send_video(chat_id, file_io)
        elif file_type == "animation" or filename.lower().endswith('.gif'):
            msg = await client.send_animation(chat_id, file_io)
        elif file_type == "audio" or filename.lower().endswith(('.mp3', '.m4a', '.ogg', '.opus')):
            msg = await client.send_audio(chat_id, file_io)
        else:
            msg = await client.send_document(chat_id, file_io)

        if not msg:
            return None
        res = {"message_id": msg.id}
        
        media = getattr(msg, msg.media.value) if msg.media else None
        if media:
            res["file_id"] = getattr(media, "file_id", None)
            thumb = getattr(media, "thumbs", [None])[0] if hasattr(media, "thumbs") else None
            res["thumb_id"] = getattr(thumb, "file_id", None)
            
        return res

    except Exception as e:
        logger.error(f"❌ [MTProto] Upload failed: {e}")
        return None
