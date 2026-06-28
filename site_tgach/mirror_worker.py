import asyncio
import logging
import os
import httpx 
import tempfile
from common.async_file_io import write_async_iter_bytes_to_file
from common.database import (
    get_pending_mirror_tasks, reschedule_mirror_task, remove_mirror_task, 
    add_file_mirror, get_file_owner_id, get_file_mirrors 
)
from common.db_pool import get_pool
from site_tgach.catbox import upload_url_to_catbox, upload_file_to_catbox
from common.bot_pool import global_bot_pool
from common.board_config import BOARD_CONFIG
from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramBadRequest
from site_tgach.mtproto_client import download_file_mtproto
from site_tgach.zeroxzero import is_0x0_available, upload_url_to_0x0, upload_file_to_0x0

logger = logging.getLogger("mirror_worker")
_INTERNAL_FILE_BOTS: dict[int, Bot] = {}

def _bot_id_from_token(token: str | None) -> int | None:
    if not token or ':' not in str(token):
        return None
    try:
        return int(str(token).split(':', 1)[0])
    except (TypeError, ValueError):
        return None

def _get_internal_file_bot(token: str) -> Bot | None:
    bot_id = _bot_id_from_token(token)
    if not bot_id:
        return None
    bot = _INTERNAL_FILE_BOTS.get(bot_id)
    if bot:
        return bot
    bot = Bot(token=token, session=AiohttpSession())
    _INTERNAL_FILE_BOTS[bot_id] = bot
    return bot

def _resolve_file_bot(owner_id: int | None) -> tuple[Bot | None, bool]:
    if owner_id and global_bot_pool:
        bot = global_bot_pool.get_bot_by_id(owner_id)
        if bot:
            return bot, True

    if owner_id:
        for board in (BOARD_CONFIG or {}).values():
            if not isinstance(board, dict):
                continue
            token = board.get('token')
            if _bot_id_from_token(token) == owner_id:
                return _get_internal_file_bot(token), False

    if global_bot_pool:
        return global_bot_pool.get_main_bot(), True
    return None, True

async def close_internal_file_bots():
    for bot in list(_INTERNAL_FILE_BOTS.values()):
        try:
            await bot.session.close()
        except Exception:
            pass
    _INTERNAL_FILE_BOTS.clear()

async def _find_msg_info(file_id: str):
    from common.db_pool import get_pool, db_lock # Локальный импорт
    try:
        async with db_lock:
            db = await get_pool()
            query = """
                SELECT cc.channel_id, cc.message_id, p.post_num
                FROM Posts p
                LEFT JOIN ChannelCopies cc ON p.post_num = cc.post_num
                WHERE p.post_num > (SELECT MAX(post_num) - 20000 FROM Posts)
                  AND instr(p.content, ?) > 0
                ORDER BY p.post_num DESC
                LIMIT 1
            """
            async with db.execute(query, (file_id,)) as cursor:
                return await cursor.fetchone()
    except Exception as e:
        logger.error(f"DB lookup error: {e}")
        return None

async def _process_single_task(task):
    file_id, mirror_type, task_id, attempt = task['file_id'], task['mirror_type'], task['id'], task['attempts']
    
    try:
        if mirror_type == '0x0' and not is_0x0_available():
            await reschedule_mirror_task(task_id, attempt)
            return

        # 0. Защита от бесконечных циклов
        if attempt > 10: 
            logger.warning(f"🗑️ Removing stale task {task_id}: max attempts reached.")
            await remove_mirror_task(task_id)
            return
        
        # 0. ПРОВЕРКА: Если зеркало уже существует
        existing_mirrors = await get_file_mirrors(file_id)
        if existing_mirrors and mirror_type in existing_mirrors:
            await remove_mirror_task(task_id)
            logger.info(f"⏭️ Skip {file_id[:8]} ({mirror_type}): already exists.")
            return

        msg_info = await _find_msg_info(file_id)
        c_id, m_id, p_num = msg_info if msg_info else (None, None, "???")
        
        owner_id = await get_file_owner_id(file_id)
        bot, public_safe_bot = _resolve_file_bot(owner_id)
        if not bot:
            await reschedule_mirror_task(task_id, attempt)
            return

        success_link = None
        file_ext = ".dat"
        fresh_file_id = file_id 
        download_success = False 
        
        file_info = None

        try:
            file_info = await bot.get_file(file_id)
            fresh_file_id = file_info.file_id 
            
            if getattr(file_info, "file_path", None):
                _, ext = os.path.splitext(file_info.file_path)
                if ext: file_ext = ext

            if public_safe_bot:
                tg_url = f"https://api.telegram.org/file/bot{bot.token}/{file_info.file_path}"
                if mirror_type == 'catbox':
                    success_link = await upload_url_to_catbox(tg_url)
                elif mirror_type == '0x0':
                    success_link = await upload_url_to_0x0(tg_url)
        except Exception as e:
            err_str = str(e).lower()
            if "logged out" in err_str or "unauthorized" in err_str or "token is invalid" in err_str:
                logger.error(f"🚨 Bot {bot.token[:10]}... is logged out/unauthorized. Disabling.")
                if global_bot_pool:
                    global_bot_pool.mark_bot_dead_by_token(bot.token)
                await reschedule_mirror_task(task_id, attempt)
                return

            is_photo = file_id.startswith("AgAC")
            if "file_id_invalid" in err_str or "wrong file_id" in err_str:
                if not msg_info: 
                    logger.error(f"🗑️ File {file_id[:10]} is DEAD (No msg context). Removing task.")
                    await remove_mirror_task(task_id)
                    return
                elif not is_photo:
                    logger.error(f"🗑️ File {file_id[:10]} is invalid and not a photo. Removing.")
                    await remove_mirror_task(task_id)
                    return
                else:
                    logger.warning(f"⚠️ Bot API rejected {file_id[:10]}. Trying recovery via MTProto/Msg...")
            else:
                logger.warning(f"⚠️ Bot API error for {file_id[:10]}: {e}") 
        
        fd, lpath = tempfile.mkstemp(prefix=f"dvach_mirror_{task_id}_", suffix=file_ext)
        os.close(fd)
        
        try:
            if not success_link:
                if msg_info:
                    c_id, m_id, _ = msg_info
                else:
                    c_id, m_id = None, None
                
                # 1. MTProto
                if await download_file_mtproto(bot.token, fresh_file_id, lpath, chat_id=c_id, message_id=m_id):
                    download_success = True
                else:
                    # 2. HTTP Fallback (если MTProto не справился)
                    logger.warning(f"⚠️ MTProto failed for {file_id[:10]}. Trying HTTP Fallback...")
                    try:
                        # Получаем путь, если его нет (или если первый запрос упал)
                        if not file_info or not getattr(file_info, "file_path", None):
                            file_info = await bot.get_file(fresh_file_id)
                        
                        file_path = getattr(file_info, "file_path", None) if file_info else None
                        if file_path:
                            dl_url = f"https://api.telegram.org/file/bot{bot.token}/{file_path}"
                            
                            transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0", retries=2)
                            async with httpx.AsyncClient(timeout=60.0, verify=False, transport=transport) as client:
                                async with client.stream("GET", dl_url) as r:
                                    if r.status_code == 200:
                                        await write_async_iter_bytes_to_file(r.aiter_bytes(), lpath)
                                        download_success = True
                                        logger.info(f"📥 HTTP Download success for {file_id[:10]}")
                                    else:
                                        logger.error(f"❌ HTTP Download failed: {r.status_code}")
                        else:
                             logger.error("❌ HTTP Fallback failed: Could not get file_path")

                    except Exception as e:
                        logger.error(f"❌ HTTP Fallback crashed: {e}")

                # 3. Загрузка (если скачали)
                if download_success:
                    if mirror_type == 'catbox':
                        success_link = await upload_file_to_catbox(lpath)
                    elif mirror_type == '0x0':
                        success_link = await upload_file_to_0x0(lpath)
                else:
                    logger.warning(f"⛔ All download methods failed for {file_id[:10]}. Rescheduling.")
                    await reschedule_mirror_task(task_id, attempt)
                    return 

        finally:
            if os.path.exists(lpath):
                try: os.remove(lpath)
                except: pass
            
        if success_link:
            await add_file_mirror(file_id, mirror_type, success_link)
            await remove_mirror_task(task_id)
            logger.info(f"✅ Post #{p_num} | Mirrored {mirror_type}: {file_id[:10]}... -> {success_link}")
        else:
            if download_success:
                await reschedule_mirror_task(task_id, attempt)

    except Exception as e:
        logger.error(f"Task {task_id} error: {e}")
        await reschedule_mirror_task(task_id, attempt)
async def process_mirror_queue():
    logger.info("mirror_worker started (Parallel Mode)")
    
    # Блок сброса таймеров УДАЛЕН для предотвращения шторма при рестарте

    SEM = asyncio.Semaphore(5) 

    async def runner(task):
        async with SEM:
            await _process_single_task(task)

    try:
        while True:
            try:
                tasks = await get_pending_mirror_tasks(limit=5)
                if not tasks:
                    await asyncio.sleep(10)
                    continue
                await asyncio.gather(*[runner(t) for t in tasks])
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Mirror worker loop crash: {e}")
                await asyncio.sleep(10)
    finally:
        await close_internal_file_bots()
