import asyncio
import logging
import os
import time
import shutil
import httpx
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
from site_tgach.mtproto_client import download_file_mtproto

logger = logging.getLogger("hf_batcher")
BATCH_SIZE = 66
MAX_WAIT_TIME = 12 * 60
CONCURRENCY_LIMIT = 8
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
            WHERE p.content LIKE ? ESCAPE '@'
            ORDER BY p.post_num DESC
            LIMIT 1
        """
        escaped_file_id = str(file_id).replace('@', '@@').replace('%', '@%').replace('_', '@_')
        search_pattern = '%' + escaped_file_id + '%'
        async with db.execute(query, (search_pattern,)) as cursor:
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
    strategies = [
        {"name": "Proxy", "env": {"HTTPS_PROXY": PROXY_URL, "HTTP_PROXY": PROXY_URL}},
        {"name": "Direct/System", "env": {}}
    ]
    for strategy in strategies:
        try:
            os.environ.pop("HTTPS_PROXY", None); os.environ.pop("HTTP_PROXY", None)
            os.environ.update(strategy["env"])
            
            api = HfApi(token=token)
            api.upload_folder(folder_path=folder, path_in_repo="media", repo_id=repo, repo_type="dataset", commit_message=f"Batch {int(time.time())}")
            logger.info(f"✅ HF Batch Upload Success ({strategy['name']})")
            return True
        except Exception as e:
            logger.warning(f"HF Batch Upload ({strategy['name']}) failed: {e}")
            continue
    return False

async def _download_http_safe(url, path):
    strategies = [{"proxy": PROXY_URL, "name": "Proxy"}, {"proxy": None, "name": "Direct"}]
    for strat in strategies:
        try:
            transport = AsyncHTTPTransport(local_address="0.0.0.0")
            async with httpx.AsyncClient(timeout=60.0, proxy=strat["proxy"], transport=transport, verify=False) as client:
                async with client.stream("GET", url) as r:
                    if r.status_code == 200:
                        await write_async_iter_bytes_to_file(r.aiter_bytes(), path)
                        return True
        except:
            continue
    return False

async def process_queue_batch():
    count, oldest_ts = await get_queue_stats()
    if count == 0:
        return
    if count < BATCH_SIZE and (time.time() - oldest_ts < MAX_WAIT_TIME):
        return

    file_ids = await get_hf_queue_batch(BATCH_SIZE)
    if not file_ids: return

    file_details = await get_file_details_batch(file_ids)
    # Удаляем проверку "if not file_details", так как для превью деталей в БД нет, и это нормально.
    
    logger.info(f"📦 Starting HF Batch for {len(file_ids)} files...")
    temp_dir = f"temp_hf_{int(time.time())}"
    os.makedirs(temp_dir, exist_ok=True)
    
    try:
        successful_files = [] 
        semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
        
        async def _download_task(fid, details):
            async with semaphore:
                try:
                    owner_id = await get_file_owner_id(fid)
                    bot = global_bot_pool.get_bot_by_id(owner_id) if owner_id else global_bot_pool.get_main_bot()
                    if not bot: return None
                    
                    # Предварительное имя (может измениться, если details нет)
                    sub = fid[:2]
                    fname_db = details.get("filename") if details else None
                    
                    fdir = os.path.join(temp_dir, sub); os.makedirs(fdir, exist_ok=True)
                    
                    fresh_file_id = fid
                    final_filename = fname_db

                    try:
                        # 1. Получаем инфо от ТГ (путь и расширение)
                        finfo = await bot.get_file(fid)
                        fresh_file_id = finfo.file_id
                        
                        # Если имени нет в БД (это превью), берем расширение из ТГ
                        if not final_filename:
                            ext = os.path.splitext(finfo.file_path)[1]
                            if not ext: ext = ".jpg" # Фолбек для фото
                            final_filename = f"{fid}{ext}"
                            
                        lpath = os.path.abspath(os.path.join(fdir, final_filename))

                        # 2. Пробуем скачать обычным HTTP
                        if await _download_http_safe(f"https://api.telegram.org/file/bot{bot.token}/{finfo.file_path}", lpath):
                            return (fid, final_filename, sub)
                            
                    except Exception as e:
                        if "file is too big" not in str(e).lower() and "file_id_invalid" in str(e).lower():
                            return (fid, "deleted", sub)

                    # 3. MTProto Fallback
                    # Если имени все еще нет (MTProto скачивание без get_file), ставим .dat
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
                    
                    return None
                except Exception as e:
                    logger.error(f"Download task error for {fid}: {e}")
                    return None

        tasks = [_download_task(fid, file_details.get(fid)) for fid in file_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, r in enumerate(results):
            if isinstance(r, tuple) and r:
                if r[1] != "deleted":
                    successful_files.append(r)

        await remove_from_hf_queue(file_ids)

        if not successful_files:
            return

        pair = hf_accounts.get_pair()
        if not pair:
            return
        token, repo = pair
        
        logger.info(f"⬆️ Uploading batch ({len(successful_files)} files) to HF repo '{repo}'...")
        if await asyncio.get_running_loop().run_in_executor(None, upload_folder_sync, temp_dir, token, repo):
            for fid, fname, sub in successful_files:
                await add_file_mirror(fid, 'huggingface', f"https://huggingface.co/datasets/{repo}/resolve/main/media/{sub}/{fname}")
            logger.info("✅ HF Batch Upload Complete.")
    
    except Exception as e:
        logger.error(f"❌ Batch processing critical error: {e}")
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)

async def hf_batch_loop():
    logger.info("🚀 HF Batcher Daemon Started")
    cleanup_stale_temp_dirs()
    await asyncio.sleep(30) 
    
    while True:
        try:
            await process_queue_batch()
            # Пауза между проверками, чтобы не грузить CPU/DB, если очередь пуста
            # (внутри process_queue_batch есть свои проверки лимитов, но пауза снаружи полезна)
            await asyncio.sleep(20) 
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"HF Batcher Loop Crash: {e}", exc_info=True)
            await asyncio.sleep(60)
