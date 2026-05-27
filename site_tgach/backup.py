import asyncio
import logging
import os
import shutil
import zipfile
import time
from datetime import datetime
from aiogram.types import FSInputFile
from aiogram.exceptions import TelegramRetryAfter

from common.db_pool import get_pool
from site_tgach.admin_config import ADMIN_IDS
import aiosqlite

logger = logging.getLogger("backup_daemon")

# Интервал: 12 часов
BACKUP_INTERVAL = 12 * 3600 

def _pack_and_split_sync(backup_db_path: str, zip_name_base: str):
    """
    Синхронная функция для тяжелых операций CPU/Disk.
    Запускается в отдельном потоке.
    """
    created_files = []
    parts_to_send = []
    
    # 1. Архивирование
    with zipfile.ZipFile(zip_name_base, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(backup_db_path, arcname="dvach_bot.db")
    created_files.append(zip_name_base)
    
    # 2. Разделение
    CHUNK_SIZE = 45 * 1024 * 1024
    file_size = os.path.getsize(zip_name_base)
    
    if file_size > CHUNK_SIZE:
        part_num = 1
        with open(zip_name_base, 'rb') as f:
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk: break
                part_name = f"{zip_name_base}.{part_num:03d}"
                with open(part_name, 'wb') as p:
                    p.write(chunk)
                parts_to_send.append(part_name)
                created_files.append(part_name)
                part_num += 1
        
        # Удаляем оригинал большого зипа, чтобы не занимал место,
        # так как мы его уже нарезали
        if os.path.exists(zip_name_base):
            os.remove(zip_name_base)
    else:
        parts_to_send.append(zip_name_base)
        
    return parts_to_send, created_files

async def create_db_backup(bot):
    if not ADMIN_IDS:
        logger.warning("⚠️ Admin IDs not set, skipping backup.")
        return
    
    backup_db_path = f"backup_{int(time.time())}.db"
    zip_name_base = f"TGACH_Backup_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.zip"
    created_files = []

    logger.info("📦 Starting ATOMIC DB backup (Threaded)...")
    
    try:
        # 1. Создание атомарного бэкапа (IO bound, асинхронно)
        source_db = await get_pool()
        async with aiosqlite.connect(backup_db_path) as backup_db:
            await source_db.backup(backup_db)
        created_files.append(backup_db_path)
        
        # 2. Сжатие и нарезка (CPU bound, в отдельном потоке)
        # Это предотвратит фриз сервера на 3-5 секунд
        parts_to_send, packed_files = await asyncio.to_thread(
            _pack_and_split_sync, backup_db_path, zip_name_base
        )
        created_files.extend(packed_files)

        # 3. Отправка админам (Network bound, асинхронно)
        for admin_id in ADMIN_IDS:
            for i, part_path in enumerate(parts_to_send):
                caption = (
                    f"📦 <b>Auto-Backup</b> (Part {i+1}/{len(parts_to_send)})\n"
                    f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
                )
                try:
                    input_file = FSInputFile(part_path, filename=os.path.basename(part_path))
                    await bot.send_document(chat_id=admin_id, document=input_file, caption=caption, parse_mode="HTML")
                    await asyncio.sleep(2) 
                except TelegramRetryAfter as e:
                    logger.warning(f"FloodWait sending backup to {admin_id}, waiting {e.retry_after}s...")
                    await asyncio.sleep(e.retry_after + 2)
                    input_file = FSInputFile(part_path, filename=os.path.basename(part_path))
                    await bot.send_document(chat_id=admin_id, document=input_file, caption=caption, parse_mode="HTML")
                except Exception as e:
                    logger.error(f"Failed to send {part_path} to {admin_id}: {e}")

        logger.info("✅ Backup broadcast completed.")

    except Exception as e:
        logger.error(f"❌ Backup generation failed: {e}", exc_info=True)

    finally:
        # 4. Очистка временных файлов
        for f in created_files:
            if os.path.exists(f):
                try: os.remove(f)
                except: pass

async def backup_loop(bot):
    """Фоновая задача"""
    logger.info("🛡️ Backup Daemon started (12h interval).")
    # Первый бэкап через 10 часов, чтобы не грузить при рестарте
    await asyncio.sleep(36000) 
    
    while True:
        await create_db_backup(bot)
        await asyncio.sleep(BACKUP_INTERVAL)