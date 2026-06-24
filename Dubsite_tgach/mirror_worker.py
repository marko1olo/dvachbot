import asyncio
import logging
import os
from common.database import (
    get_pending_mirror_tasks, reschedule_mirror_task, remove_mirror_task, 
    add_file_mirror, get_file_owner_id, get_file_mirrors 
)
from common.db_pool import get_pool
from site_tgach.catbox import upload_url_to_catbox, upload_file_to_catbox
from common.bot_pool import global_bot_pool
from aiogram.exceptions import TelegramBadRequest
from site_tgach.mtproto_client import download_file_mtproto

logger = logging.getLogger("mirror_worker")

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
        # 0. Защита от бесконечных циклов
        if attempt > 5:  # Снижаем лимит попыток до 5
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
        bot = global_bot_pool.get_bot_by_id(owner_id) if owner_id else global_bot_pool.get_main_bot()
        if not bot:
            await reschedule_mirror_task(task_id, attempt)
            return

        success_link = None
        file_ext = ".dat"
        fresh_file_id = file_id 
        download_success = False # Флаг успешного скачивания
        
        try:
            file_info = await bot.get_file(file_id)
            fresh_file_id = file_info.file_id 
            
            file_path = getattr(file_info, "file_path", None)
            if file_path:
                _, ext = os.path.splitext(file_path)
                if ext: file_ext = ext

                tg_url = f"https://api.telegram.org/file/bot{bot.token}/{file_path}"
                if mirror_type == 'catbox':
                    success_link = await upload_url_to_catbox(tg_url)
        except TelegramBadRequest as e:
            if "file_id_invalid" in str(e).lower() or "wrong file_id" in str(e).lower():
                logger.error(f"❌ File {file_id[:10]} is dead in TG. Removing task.")
                await remove_mirror_task(task_id)
                return
        except Exception:
            pass 
        
        lpath = os.path.abspath(f"temp_mw_{task_id}{file_ext}")
        
        try:
            if not success_link:
                if msg_info:
                    c_id, m_id, _ = msg_info
                else:
                    c_id, m_id = None, None
                
                # Пробуем скачать через MTProto
                if await download_file_mtproto(bot.token, fresh_file_id, lpath, chat_id=c_id, message_id=m_id):
                    download_success = True
                    if mirror_type == 'catbox':
                        success_link = await upload_file_to_catbox(lpath)
                else:
                    # Если MTProto не смог скачать (вернул False), считаем файл битым/недоступным
                    logger.warning(f"⚠️ MTProto download failed for {file_id[:10]}. Removing task to prevent loop.")
                    await remove_mirror_task(task_id)
                    return # ВЫХОД, чтобы не планировать повтор
                    
        finally:
            if os.path.exists(lpath):
                try: os.remove(lpath)
                except: pass
            
        if success_link:
            await add_file_mirror(file_id, mirror_type, success_link)
            await remove_mirror_task(task_id)
            logger.info(f"✅ Post #{p_num} | Mirrored {mirror_type}: {file_id[:10]}... -> {success_link}")
        else:
            # Если скачалось, но не залилось (ошибка Catbox) - повторяем
            if download_success:
                await reschedule_mirror_task(task_id, attempt)
            else:
                # Если даже не скачалось (и мы не вышли раньше) - удаляем
                await remove_mirror_task(task_id)

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

    while True:
        try:
            tasks = await get_pending_mirror_tasks(limit=5)
            if not tasks:
                await asyncio.sleep(10)
                continue
            
            await asyncio.gather(*[runner(t) for t in tasks])
            
        except Exception as e:
            logger.error(f"Mirror worker loop crash: {e}")
            await asyncio.sleep(10)