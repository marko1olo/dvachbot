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
from site_tgach.catbox import upload_url_to_catbox, upload_file_to_catbox
from common.bot_pool import global_bot_pool
from common.board_config import BOARD_CONFIG
from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
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
            # No post_num window limit - search full table for old restored posts too
            query = """
                SELECT cc.channel_id, cc.message_id, p.post_num
                FROM Posts p
                LEFT JOIN ChannelCopies cc ON p.post_num = cc.post_num
                WHERE instr(p.content, ?) > 0
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

        msg_info = None
        msg_info_fetched = False
        p_num = "???"

        async def get_msg_info_deferred():
            nonlocal msg_info, msg_info_fetched, p_num
            if not msg_info_fetched:
                msg_info = await _find_msg_info(file_id)
                msg_info_fetched = True
                if msg_info:
                    p_num = msg_info[2]
            return msg_info

        logger.info(f"DEBUG: [Task {task_id}] Started for {file_id[:10]}...")
        owner_id = await get_file_owner_id(file_id)
        logger.info(f"DEBUG: [Task {task_id}] get_file_owner_id done (owner={owner_id})")
        bot, public_safe_bot = _resolve_file_bot(owner_id)
        if not bot:
            logger.info(f"DEBUG: [Task {task_id}] bot not found, rescheduling")
            await reschedule_mirror_task(task_id, attempt)
            return

        success_link = None
        file_ext = ".dat"
        fresh_file_id = file_id 
        download_success = False 
        
        file_info = None

        try:
            logger.info(f"DEBUG: [Task {task_id}] Calling bot.get_file...")
            file_info = await bot.get_file(file_id)
            logger.info(f"DEBUG: [Task {task_id}] bot.get_file success: {getattr(file_info, 'file_path', None)}")
            fresh_file_id = file_info.file_id 
            
            file_path = getattr(file_info, "file_path", None)
            if file_path:
                _, ext = os.path.splitext(file_path)
                if ext: file_ext = ext

                if public_safe_bot:
                    tg_url = f"https://api.telegram.org/file/bot{bot.token}/{file_path}"
                    if mirror_type == 'catbox':
                        logger.info(f"DEBUG: [Task {task_id}] Uploading URL to Catbox...")
                        success_link = await upload_url_to_catbox(tg_url)
                        logger.info(f"DEBUG: [Task {task_id}] Upload URL result: {success_link}")
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
                await get_msg_info_deferred()
                if not is_photo and not msg_info:
                    # Non-photo, no context at all - truly dead
                    logger.error(f"🗑️ File {file_id[:10]} is DEAD (non-photo, no msg context). Removing task.")
                    await remove_mirror_task(task_id)
                    return
                elif not is_photo:
                    logger.error(f"🗑️ File {file_id[:10]} is invalid and not a photo. Removing.")
                    await remove_mirror_task(task_id)
                    return
                elif is_photo and not msg_info:
                    logger.error(f"🗑️ File {file_id[:10]} is DEAD (photo rejected by Bot API, and no msg context for MTProto). Removing task.")
                    await remove_mirror_task(task_id)
                    return
                else:
                    logger.warning(f"⚠️ Bot API rejected photo {file_id[:10]}. Trying MTProto recovery...")
            else:
                logger.warning(f"⚠️ Bot API error for {file_id[:10]}: {e}") 
        
        fd, lpath = tempfile.mkstemp(prefix=f"dvach_mirror_{task_id}_", suffix=file_ext)
        os.close(fd)
        
        try:
            if not success_link:
                await get_msg_info_deferred()
                if msg_info:
                    c_id, m_id, _ = msg_info
                else:
                    c_id, m_id = None, None
                
                # 1. MTProto (skip for photos without context since it always fails in pyrogram)
                use_mtproto = not (fresh_file_id.startswith("AgAC") and not (c_id and m_id))
                if use_mtproto and await download_file_mtproto(bot.token, fresh_file_id, lpath, chat_id=c_id, message_id=m_id):
                    download_success = True
                else:
                    if not use_mtproto:
                        logger.info(f"⏭️ Skipping MTProto for {file_id[:10]} (photo without context). Trying HTTP download directly.")
                    else:
                        logger.warning(f"⚠️ MTProto failed for {file_id[:10]}. Trying HTTP Fallback...")
                    try:
                        # Получаем путь, если его нет (или если первый запрос упал)
                        if file_info is None:
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
                    fsize = os.path.getsize(lpath)
                    if mirror_type == 'catbox' and fsize > 200 * 1024 * 1024:
                        logger.warning(f"⚠️ File {file_id[:10]} is too large for Catbox ({fsize / 1024 / 1024:.1f} MB). Skipping upload and removing task.")
                        await remove_mirror_task(task_id)
                        return
                    elif mirror_type == '0x0' and fsize > 512 * 1024 * 1024:
                        logger.warning(f"⚠️ File {file_id[:10]} is too large for 0x0 ({fsize / 1024 / 1024:.1f} MB). Skipping upload and removing task.")
                        await remove_mirror_task(task_id)
                        return

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

    SEM = asyncio.Semaphore(20) 

    async def runner(task):
        async with SEM:
            await asyncio.create_task(_process_single_task(task))

    try:
        while True:
            try:
                allowed_types = ['catbox']
                if is_0x0_available():
                    allowed_types.append('0x0')

                tasks = await get_pending_mirror_tasks(limit=20, allowed_types=allowed_types)
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
