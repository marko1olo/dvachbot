import asyncio
import logging
import os
import time
import shutil
import httpx
import hashlib
from httpx import AsyncHTTPTransport
from huggingface_hub import HfApi
from common.async_file_io import write_async_iter_bytes_to_file
from common.db_pool import get_pool
from common.bot_pool import global_bot_pool
from common.config import STORAGE_CHANNELS
from common.database import (
    get_hf_queue_batch, get_queue_stats, remove_from_hf_queue, add_file_mirror, get_file_owner_id,
    get_file_details_batch
)
from common.token_pool import hf_accounts
from site_tgach.mirror_health import clear_hf_failure, is_hf_repo_available, mark_hf_upload_failure
from site_tgach.mtproto_client import download_file_mtproto

logger = logging.getLogger("hf_batcher")
BATCH_SIZE = 77
MAX_WAIT_TIME = 3 * 60
CONCURRENCY_LIMIT = 20
HF_COOLDOWN_UNTIL = 0
PROXY_URL = os.getenv("HTTPS_PROXY") or "http://127.0.0.1:10808"

def cleanup_stale_temp_dirs():
    try:
        current_dir = os.getcwd()
        count = 0
        for name in os.listdir(current_dir):
            if name.startswith("temp_hf_") and os.path.isdir(name):
                try:
                    shutil.rmtree(name, ignore_errors=True)
                    count += 1
                except: pass
        if count > 0:
            logger.info(f"🧹 Startup Cleanup: Removed {count} stale temp folders.")
    except Exception as e:
        logger.error(f"Startup cleanup error: {e}")

async def find_file_message_info(file_id):
    try:
        db = await get_pool()
        query = """
            SELECT cc.channel_id, cc.message_id, p.post_num
            FROM Posts p
            JOIN ChannelCopies cc ON p.post_num = cc.post_num
            WHERE instr(p.content, ?) > 0
            ORDER BY p.post_num DESC
            LIMIT 1
        """
        async with db.execute(query, (file_id,)) as cursor:
            return await cursor.fetchone()
    except:
        return None

async def refresh_reference_by_send(bot, file_id):
    try:
        target = STORAGE_CHANNELS.get('ru')
        msg = await bot.send_video(chat_id=target, video=file_id, disable_notification=True)
        return target, msg.message_id
    except:
        try:
            target = STORAGE_CHANNELS.get('ru')
            msg = await bot.send_document(chat_id=target, document=file_id, disable_notification=True)
            return target, msg.message_id
        except:
            return None

def upload_folder_sync(folder, token, repo):
    global HF_COOLDOWN_UNTIL
    strategies = [
        {"name": "Direct/System", "env": {}},
        {"name": "Proxy", "env": {"HTTPS_PROXY": PROXY_URL, "HTTP_PROXY": PROXY_URL}}
    ]
    for strategy in strategies:
        try:
            os.environ.pop("HTTPS_PROXY", None) 
            os.environ.pop("HTTP_PROXY", None)
            os.environ.update(strategy["env"])
            
            # ПРАВКА: Увеличиваем внутренние ретраи библиотеки для тяжелых файлов
            api = HfApi(token=token)
            api.upload_folder(
                folder_path=folder, 
                repo_id=repo, 
                repo_type="dataset"
            )
            clear_hf_failure(repo)
            logger.info(f"✅ HF Batch Upload Success ({strategy['name']})")
            return True
        except Exception as e:
            err_msg = str(e).lower()
            # ПРАВКА: Если лимит или обрыв протокола — не мучаем другие стратегии
            if "429" in err_msg or "rate limit" in err_msg:
                logger.error(f"🚨 HF Rate Limit hit (429). Activating 30m cooldown.")
                HF_COOLDOWN_UNTIL = time.time() + 1800
                break # Выходим из цикла стратегий
            
            if "unexpected_eof" in err_msg or "timeout" in err_msg:
                logger.error(f"❌ HF Network Timeout/EOF on strategy {strategy['name']}. Batch too heavy?")
                # Не выходим, пробуем следующую (прокси может быть стабильнее)
                
            if mark_hf_upload_failure(e, repo):
                break

            logger.warning(f"HF Batch Upload ({strategy['name']}) failed: {e}") 
            continue
    
    return False

async def _download_http_safe(url, path):
    strategies = [{"proxy": PROXY_URL, "name": "Proxy"}, {"proxy": None, "name": "Direct"}]
    for strat in strategies:
        try:
            transport = AsyncHTTPTransport(local_address="0.0.0.0")
            async with httpx.AsyncClient(timeout=300.0, proxy=strat["proxy"], transport=transport, verify=False) as client:
                async with client.stream("GET", url) as r:
                    if r.status_code == 200:
                        await write_async_iter_bytes_to_file(r.aiter_bytes(), path)
                        return True
        except:
            continue
    return False

async def process_queue_batch():
    if time.time() < HF_COOLDOWN_UNTIL:
        return

    # ПРАВКА: Проверяем наличие рабочих аккаунтов ДО того, как начнем качать файлы из ТГ
    token, repo = hf_accounts.get_pair()
    if not token or not repo:
        if time.time() % 300 < 20: # Логируем раз в 5 минут, чтобы не спамить
            logger.warning("⚠️ HF Batcher: No active HuggingFace accounts found in HF_ACCOUNTS.")
        return
    if not is_hf_repo_available(repo):
        if time.time() % 300 < 20:
            logger.warning("HF Batcher: repo is temporarily disabled by mirror health: %s", repo)
        return

    count, oldest_ts = await get_queue_stats()
    if count == 0:
        return
    if count < BATCH_SIZE and (time.time() - oldest_ts < MAX_WAIT_TIME):
        return

    file_ids = await get_hf_queue_batch(BATCH_SIZE)
    if not file_ids: return

    file_details = await get_file_details_batch(file_ids)
    
    logger.info(f"📦 Starting HF Batch for {len(file_ids)} files...")
    temp_dir = f"temp_hf_{int(time.time())}"
    media_root = os.path.join(temp_dir, "media")
    os.makedirs(media_root, exist_ok=True)
    
    try:
        successful_files = [] 
        semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
        
        async def _download_task(fid, details):
            async with semaphore:
                try:
                    owner_id = await get_file_owner_id(fid)
                    bot = global_bot_pool.get_bot_by_id(owner_id) if owner_id else global_bot_pool.get_main_bot()
                    if not bot: return None
                    
                    sub = hashlib.md5(fid.encode()).hexdigest()[:2]
                    fname_db = details.get("filename") if details else None
                    
                    fdir = os.path.join(media_root, sub); os.makedirs(fdir, exist_ok=True)
                    
                    fresh_file_id = fid
                    final_filename = fname_db

                    try:
                        finfo = await bot.get_file(fid)
                        fresh_file_id = finfo.file_id
                        
                        file_path = getattr(finfo, "file_path", None)
                        if file_path:
                            if not final_filename:
                                ext = os.path.splitext(file_path)[1]
                                if not ext: ext = ".jpg"
                                final_filename = f"{fid}{ext}"

                            lpath = os.path.abspath(os.path.join(fdir, final_filename))

                            if await _download_http_safe(f"https://api.telegram.org/file/bot{bot.token}/{file_path}", lpath):
                                return (fid, final_filename, sub)
                            
                    except Exception as e:
                        err_str = str(e).lower()
                        if "logged out" in err_str or "unauthorized" in err_str or "token is invalid" in err_str:
                            logger.error(f"🚨 Bot {bot.token[:10]}... is logged out/unauthorized. Disabling.")
                            if global_bot_pool:
                                global_bot_pool.mark_bot_dead_by_token(bot.token)
                            return None

                        fatal_errors = ["file_id_invalid", "wrong file_id", "not found", "invalid", "bad request"]
                        if any(x in err_str for x in fatal_errors):
                            logger.error(f"🗑️ File {fid[:10]} is DEAD in Telegram. Marking for removal.")
                            return (fid, "deleted", sub)
                        
                        return None

                    if not final_filename:
                        final_filename = f"{fid}.dat"
                        
                    lpath = os.path.abspath(os.path.join(fdir, final_filename))

                    info = await find_file_message_info(fid)
                    c_id, m_id = None, None
                    if info:
                        c_id, m_id, _ = info
                    else:
                        res = await refresh_reference_by_send(bot, fid)
                        if res: c_id, m_id = res
                    
                    if c_id and await download_file_mtproto(bot.token, fresh_file_id, lpath, c_id, m_id):
                        return (fid, final_filename, sub)
                    
                    logger.error(f"❌ All download methods failed for {fid[:10]}. Removal.")
                    return (fid, "deleted", sub)
                except Exception as e:
                    logger.error(f"Download task error for {fid}: {e}")
                    return None

        tasks = [_download_task(fid, file_details.get(fid)) for fid in file_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        success_ids = set()
        failed_ids = set()
        
        for i, r in enumerate(results):
            original_fid = file_ids[i]
            if isinstance(r, tuple) and r:
                if r[1] != "deleted":
                    successful_files.append(r)
                    success_ids.add(r[0])
                else:
                    failed_ids.add(original_fid)
            else:
                logger.warning(f"⏳ Temporary download failure for {original_fid[:10]}. Keeping in queue.")

        if failed_ids:
            await remove_from_hf_queue(list(failed_ids))

        if not successful_files:
            return

        logger.info(f"⬆️ Uploading batch ({len(successful_files)} files) to HF repo '{repo}'...")
        
        # Передаем токен и репо, которые получили в начале функции
        if await asyncio.get_running_loop().run_in_executor(None, upload_folder_sync, temp_dir, token, repo):
            await remove_from_hf_queue(list(success_ids))
            
            for fid, fname, sub in successful_files:
                await add_file_mirror(fid, 'huggingface', f"https://huggingface.co/datasets/{repo}/resolve/main/media/{sub}/{fname}")
            logger.info("✅ HF Batch Upload Complete.")
        else:
            logger.warning("⚠️ Batch upload failed. Files remain in queue for retry.")
    
    except Exception as e:
        logger.error(f"❌ Batch processing critical error: {e}")
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
async def hf_batch_loop():
    if os.getenv("HF_MIRRORS_DISABLED", "").strip().lower() in {"1", "true", "yes", "on"}:
        logger.info("⏸️ HF Batcher Daemon Disabled via HF_MIRRORS_DISABLED env.")
        return
    logger.info("🚀 HF Batcher Daemon Started")
    cleanup_stale_temp_dirs()
    await asyncio.sleep(30) 
    
    while True:
        try:
            await process_queue_batch()
            await asyncio.sleep(20) 
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"HF Batcher Loop Crash: {e}", exc_info=True)
            await asyncio.sleep(60)
