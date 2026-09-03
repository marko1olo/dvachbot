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
from site_tgach.catbox import upload_url_to_catbox, upload_file_to_catbox, is_catbox_available
from common.bot_pool import global_bot_pool
from common.board_config import BOARD_CONFIG
from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from site_tgach.mtproto_client import download_file_mtproto
from site_tgach.zeroxzero import is_0x0_available, upload_url_to_0x0, upload_file_to_0x0
from site_tgach.pixhost import upload_file_to_pixhost, PIXHOST_SUPPORTED_EXT, PIXHOST_MAX_MB
from site_tgach.imgbb import upload_file_to_imgbb, IMGBB_SUPPORTED_EXT
from site_tgach.freeimage import upload_file_to_freeimage

logger = logging.getLogger("mirror_worker")
_INTERNAL_FILE_BOTS: dict[int, Bot] = {}


def _detect_real_ext(filepath: str) -> str:
    """Detect real file extension from magic bytes. Returns e.g. '.jpg' or '' if unknown."""
    try:
        with open(filepath, "rb") as f:
            header = f.read(12)
        if header[:3] == b'\xFF\xD8\xFF':
            return ".jpg"
        if header[:8] == b'\x89PNG\r\n\x1a\n':
            return ".png"
        if header[:6] in (b'GIF87a', b'GIF89a'):
            return ".gif"
        if header[:4] == b'RIFF' and header[8:12] == b'WEBP':
            return ".webp"
        if header[:2] == b'BM':
            return ".bmp"
    except Exception:
        import traceback; traceback.print_exc()
    return ""

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
            import traceback; traceback.print_exc()
    _INTERNAL_FILE_BOTS.clear()

async def _find_msg_info(file_id: str):
    from common.db_pool import get_pool, db_lock # Локальный импорт
    try:
        async with db_lock:
            db = await get_pool()
            # No post_num window limit - search full table for old restored posts too
            query = """
                SELECT cc.channel_id, cc.message_id, p.post_num
                FROM PostFiles pf
                JOIN Posts p ON pf.post_num = p.post_num
                LEFT JOIN ChannelCopies cc ON p.post_num = cc.post_num
                WHERE (pf.original_file_id = ? OR pf.thumbnail_file_id = ?)
                ORDER BY p.post_num DESC
                LIMIT 1
            """
            async with db.execute(query, (file_id, file_id)) as cursor:
                return await cursor.fetchone()
    except Exception as e:
        logger.error(f"DB lookup error: {e}", exc_info=True)
        return None


async def _try_pixhost_upload(lpath: str, file_id: str, file_info) -> str | None:
    """Пытается загрузить изображение в Pixhost, проверяя размер и поддерживаемые форматы."""
    try:
        fsize = os.path.getsize(lpath)
        if fsize > PIXHOST_MAX_MB * 1024 * 1024:
            return None

        _, fext = os.path.splitext(lpath)
        target_path = lpath
        needs_cleanup = False
        if fext.lower() not in PIXHOST_SUPPORTED_EXT:
            if file_info and getattr(file_info, 'file_path', None):
                _, ext_from_tg = os.path.splitext(file_info.file_path)
                if ext_from_tg and ext_from_tg.lower() in PIXHOST_SUPPORTED_EXT:
                    fext = ext_from_tg.lower()
            if fext.lower() not in PIXHOST_SUPPORTED_EXT:
                fext = _detect_real_ext(lpath)
            if not fext and file_id.startswith("AgAC"):
                fext = ".jpg"

            if fext and fext.lower() in PIXHOST_SUPPORTED_EXT:
                new_lpath = lpath + fext.lower()
                import shutil
                shutil.copyfile(lpath, new_lpath)
                target_path = new_lpath
                needs_cleanup = True
            else:
                return None

        try:
            return await upload_file_to_pixhost(target_path)
        finally:
            if needs_cleanup and os.path.exists(target_path):
                try:
                    os.remove(target_path)
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"⚠️ Pixhost upload error for {file_id[:10]}: {e}")
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
                        if is_catbox_available():
                            logger.info(f"DEBUG: [Task {task_id}] Uploading URL to Catbox...")
                            success_link = await upload_url_to_catbox(tg_url)
                            logger.info(f"DEBUG: [Task {task_id}] Upload URL result: {success_link}")
                        else:
                            logger.info(f"DEBUG: [Task {task_id}] Catbox is paused/unavailable, skipping URL upload.")
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
                if use_mtproto and (await download_file_mtproto(bot.token, fresh_file_id, lpath, chat_id=c_id, message_id=m_id)) and os.path.exists(lpath) and os.path.getsize(lpath) > 0:
                    download_success = True
                else:
                    if not use_mtproto:
                        logger.info(f"⏭️ Skipping MTProto for {file_id[:10]} (photo without context). Trying HTTP download directly.")
                    else:
                        logger.warning(f"⚠️ MTProto failed for {file_id[:10]}. Trying HTTP Fallback...")
                    try:
                        # Получаем путь, если его нет
                        if file_info is None:
                            try:
                                file_info = await bot.get_file(fresh_file_id)
                            except Exception as gf_err:
                                logger.warning(f"⚠️ HTTP Fallback bot.get_file failed for {file_id[:10]}: {gf_err}")
                                file_info = None

                        file_path = getattr(file_info, "file_path", None) if file_info else None
                        if file_path:
                            dl_url = f"https://api.telegram.org/file/bot{bot.token}/{file_path}"

                            transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0", retries=2)
                            async with httpx.AsyncClient(timeout=60.0, verify=False, transport=transport) as client:
                                async with client.stream("GET", dl_url) as r:
                                    if r.status_code == 200:
                                        await write_async_iter_bytes_to_file(r.aiter_bytes(), lpath)
                                        if os.path.exists(lpath) and os.path.getsize(lpath) > 0:
                                            download_success = True
                                            logger.info(f"📥 HTTP Download success for {file_id[:10]}")
                                        else:
                                            download_success = False
                                            logger.warning(f"⚠️ HTTP Download received 0 bytes for {file_id[:10]}")
                                    else:
                                        logger.warning(f"⚠️ HTTP Download returned status {r.status_code} for {file_id[:10]}")
                        else:
                            logger.warning(f"⚠️ HTTP Fallback skipped for {file_id[:10]}: no file_path available")

                    except Exception as e:
                        logger.warning(f"⚠️ HTTP Fallback error for {file_id[:10]}: {e}")

                # 3. Загрузка (если скачали)
                if download_success:
                    fsize = os.path.getsize(lpath)
                    if fsize == 0:
                        logger.warning(f"⚠️ Downloaded file is empty (0 bytes) for {file_id[:10]}. Rescheduling.")
                        await reschedule_mirror_task(task_id, attempt)
                        return
                    if mirror_type == 'catbox' and fsize > 512 * 1024 * 1024:
                        logger.warning(f"⚠️ File {file_id[:10]} is too large for Catbox and fallbacks ({fsize / 1024 / 1024:.1f} MB). Skipping upload and removing task.")
                        await remove_mirror_task(task_id)
                        return
                    elif mirror_type == '0x0' and fsize > 512 * 1024 * 1024:
                        logger.warning(f"⚠️ File {file_id[:10]} is too large for 0x0 ({fsize / 1024 / 1024:.1f} MB). Skipping upload and removing task.")
                        await remove_mirror_task(task_id)
                        return
                    elif mirror_type == 'pixhost' and fsize > PIXHOST_MAX_MB * 1024 * 1024:
                        logger.warning(f"⚠️ File {file_id[:10]} is too large for Pixhost ({fsize / 1024 / 1024:.1f} MB). Removing task.")
                        await remove_mirror_task(task_id)
                        return
                    elif mirror_type == 'imgbb' and fsize > 32 * 1024 * 1024:
                        logger.warning(f"⚠️ File {file_id[:10]} is too large for ImgBB ({fsize / 1024 / 1024:.1f} MB). Removing task.")
                        await remove_mirror_task(task_id)
                        return

                    actual_mirror_type = mirror_type
                    if mirror_type == 'catbox':
                        if is_catbox_available() and fsize <= 200 * 1024 * 1024:
                            success_link = await upload_file_to_catbox(lpath)

                        if not success_link:
                            logger.warning(
                                f"⚠️ [MirrorWorker] Catbox unavailable or failed for {file_id[:10]} (size={fsize / 1024 / 1024:.2f} MB). "
                                f"Attempting cascade fallback (pixhost -> 0x0)..."
                            )
                            # 1. Фоллбек: pixhost для картинок до 10MB
                            if fsize <= PIXHOST_MAX_MB * 1024 * 1024:
                                success_link = await _try_pixhost_upload(lpath, file_id, file_info)
                                if success_link:
                                    actual_mirror_type = 'pixhost'
                                    logger.info(f"🔄 [MirrorWorker] Cascade fallback to Pixhost succeeded for {file_id[:10]}: {success_link}")

                            # 2. Фоллбек: 0x0.st для файлов до 512MB
                            if not success_link and fsize <= 512 * 1024 * 1024 and is_0x0_available():
                                success_link = await upload_file_to_0x0(lpath)
                                if success_link:
                                    actual_mirror_type = '0x0'
                                    logger.info(f"🔄 [MirrorWorker] Cascade fallback to 0x0.st succeeded for {file_id[:10]}: {success_link}")

                    elif mirror_type == '0x0':
                        success_link = await upload_file_to_0x0(lpath)
                    elif mirror_type == 'pixhost':
                        success_link = await _try_pixhost_upload(lpath, file_id, file_info)
                        if not success_link and fsize <= PIXHOST_MAX_MB * 1024 * 1024:
                            _, fext = os.path.splitext(lpath)
                            if fext.lower() not in PIXHOST_SUPPORTED_EXT and not _detect_real_ext(lpath):
                                logger.info(f"⏭️ Pixhost: cannot detect image type for {file_id[:10]} (ext={fext}). Removing task.")
                                await remove_mirror_task(task_id)
                                return
                    elif mirror_type == 'imgbb':
                        _, fext = os.path.splitext(lpath)
                        if fext.lower() not in IMGBB_SUPPORTED_EXT:
                            if file_info and getattr(file_info, 'file_path', None):
                                _, ext_from_tg = os.path.splitext(file_info.file_path)
                                if ext_from_tg and ext_from_tg.lower() in IMGBB_SUPPORTED_EXT:
                                    fext = ext_from_tg.lower()
                            if fext.lower() not in IMGBB_SUPPORTED_EXT:
                                fext = _detect_real_ext(lpath)
                            if not fext and file_id.startswith("AgAC"):
                                fext = ".jpg"

                            if fext and fext.lower() in IMGBB_SUPPORTED_EXT:
                                new_lpath = lpath + fext.lower()
                                os.rename(lpath, new_lpath)
                                lpath = new_lpath
                                logger.debug(f"🔍 ImgBB: resolved {fext} for {file_id[:10]}")
                            else:
                                logger.info(f"⏭️ ImgBB: cannot detect image type for {file_id[:10]} (ext={fext}). Removing task.")
                                await remove_mirror_task(task_id)
                                return
                        success_link = await upload_file_to_imgbb(lpath)
                    elif mirror_type == 'freeimage':
                        success_link = await upload_file_to_freeimage(lpath)
                else:
                    if attempt >= 3:
                        logger.warning(f"⛔ All download methods failed {attempt} times for {file_id[:10]}. Removing unrecoverable task.")
                        await remove_mirror_task(task_id)
                    else:
                        logger.warning(f"⛔ All download methods failed for {file_id[:10]} (attempt {attempt}/3). Rescheduling.")
                        await reschedule_mirror_task(task_id, attempt)
                    return 

        finally:
            if os.path.exists(lpath):
                try: os.remove(lpath)
                except Exception: pass
            
        if success_link:
            await add_file_mirror(file_id, actual_mirror_type, success_link)
            await remove_mirror_task(task_id)
            logger.info(f"✅ Post #{p_num} | Mirrored {actual_mirror_type}: {file_id[:10]}... -> {success_link}")
        else:
            if download_success:
                await reschedule_mirror_task(task_id, attempt)

    except Exception as e:
        logger.error(f"Task {task_id} error: {e}", exc_info=True)
        await reschedule_mirror_task(task_id, attempt)
async def process_mirror_queue():
    logger.info("mirror_worker started (Parallel Mode)")
    
    # Блок сброса таймеров УДАЛЕН для предотвращения шторма при рестарте

    SEM = asyncio.Semaphore(8)  # Снижен с 20 до 8 для уменьшения нагрузки

    async def runner(task):
        async with SEM:
            await _process_single_task(task)

    try:
        while True:
            try:
                from site_tgach.imgbb import IMGBB_API_KEY, _KEY_COOLDOWN, _is_key_available
                from site_tgach.pixhost import _pixhost_backoff_until
                import time as _time

                allowed_types = ['pixhost']
                if is_catbox_available():
                    allowed_types.append('catbox')
                if is_0x0_available():
                    allowed_types.append('0x0')
                if IMGBB_API_KEY:
                    allowed_types.append('imgbb')
                if os.getenv("FREEIMAGE_API_KEY"):
                    allowed_types.append('freeimage')

                # Если ImgBB забанил все ключи — исключаем его из пула
                all_imgbb_cooled = (
                    'imgbb' in allowed_types and
                    all(not _is_key_available(k) for k in _KEY_COOLDOWN.keys() if k in _KEY_COOLDOWN)
                    and len(_KEY_COOLDOWN) >= 3
                )
                if all_imgbb_cooled:
                    allowed_types = [t for t in allowed_types if t != 'imgbb']
                    logger.debug("[MirrorWorker] All ImgBB keys cooled down, skipping imgbb tasks this round.")

                # Если Pixhost под backoff — исключаем
                if _pixhost_backoff_until > _time.monotonic():
                    allowed_types = [t for t in allowed_types if t != 'pixhost']
                    logger.debug("[MirrorWorker] Pixhost backoff active, skipping pixhost tasks this round.")

                tasks = await get_pending_mirror_tasks(limit=8, allowed_types=allowed_types)
                if not tasks:
                    await asyncio.sleep(10)
                    continue
                await asyncio.gather(*[runner(t) for t in tasks])
                # Пауза между батчами чтобы не долбить хостинги залпом
                await asyncio.sleep(2)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Mirror worker loop crash: {e}", exc_info=True)
                await asyncio.sleep(10)
    finally:
        await close_internal_file_bots()

