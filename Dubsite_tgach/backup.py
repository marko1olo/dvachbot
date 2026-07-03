import asyncio
import logging
import os
import zipfile
import time
from datetime import datetime
from aiogram.types import BufferedInputFile
from aiogram.exceptions import TelegramRetryAfter

import aiosqlite

from common.db_pool import get_pool
from common.database import get_system_setting, set_system_setting
from site_tgach.admin_config import ADMIN_IDS

logger = logging.getLogger("backup_daemon")

# Интервал: 12 часов
BACKUP_INTERVAL = 12 * 3600 


def create_backup_archive(backup_db_path: str, zip_name_base: str) -> None:
    with zipfile.ZipFile(zip_name_base, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(backup_db_path, arcname="dvach_bot.db")


def split_file_by_size(path: str, chunk_size: int) -> list[str]:
    file_size = os.path.getsize(path)
    if file_size <= chunk_size:
        return [path]

    parts = []
    part_num = 1
    with open(path, 'rb') as source:
        while True:
            chunk = source.read(chunk_size)
            if not chunk:
                break
            part_name = f"{path}.{part_num:03d}"
            with open(part_name, 'wb') as part:
                part.write(chunk)
            parts.append(part_name)
            part_num += 1
    os.remove(path)
    return parts

async def create_db_backup(bot) -> bool:
    if not ADMIN_IDS:
        logger.warning("⚠️ Admin IDs not set, skipping backup.")
        return False
    
    backup_db_path = f"backup_{int(time.time())}.db"
    zip_name_base = f"TGACH_Backup_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.zip"
    created_files = []

    logger.info("📦 Starting ATOMIC DB backup using Online Backup API...")
    
    try:
        # 1. Создание атомарного бэкапа
        source_db = await get_pool()
        async with aiosqlite.connect(backup_db_path) as backup_db:
            await source_db.backup(backup_db)
        
        # 2. Архивирование бэкапа
        await asyncio.to_thread(create_backup_archive, backup_db_path, zip_name_base)
        created_files.append(zip_name_base)
        
        # 3. Разделение на части, если необходимо
        CHUNK_SIZE = 45 * 1024 * 1024
        file_size = os.path.getsize(zip_name_base)
        if file_size > CHUNK_SIZE:
            logger.info(f"✂️ File size {file_size/1024/1024:.2f}MB > 45MB. Splitting...")
        parts_to_send = await asyncio.to_thread(split_file_by_size, zip_name_base, CHUNK_SIZE)
        if parts_to_send != [zip_name_base]:
            created_files.remove(zip_name_base)
            created_files.extend(parts_to_send)

        # 4. Отправка админам
        for admin_id in ADMIN_IDS:
            for i, part_path in enumerate(parts_to_send):
                caption = (
                    f"📦 <b>Auto-Backup</b> (Part {i+1}/{len(parts_to_send)})\n"
                    f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
                )
                try:
                    input_file = await asyncio.to_thread(BufferedInputFile.from_file, part_path, filename=os.path.basename(part_path))
                    await bot.send_document(chat_id=admin_id, document=input_file, caption=caption, parse_mode="HTML")
                    await asyncio.sleep(1) 
                except TelegramRetryAfter as e:
                    logger.warning(f"FloodWait sending backup to {admin_id}, waiting {e.retry_after}s...")
                    await asyncio.sleep(e.retry_after + 1)
                    await bot.send_document(chat_id=admin_id, document=input_file, caption=caption, parse_mode="HTML")
                except Exception as e:
                    logger.error(f"Failed to send {part_path} to {admin_id}: {e}")

        logger.info("✅ Backup broadcast completed.")
        return True

    except Exception as e:
        logger.error(f"❌ Backup generation failed: {e}", exc_info=True)
        return False

    finally:
        # 5. Очистка временных файлов
        if os.path.exists(backup_db_path):
            os.remove(backup_db_path)
        for f in created_files:
            if os.path.exists(f):
                os.remove(f)

async def backup_loop(bot):
    """Фоновая задача"""
    logger.info("🛡️ Backup Daemon started (12h interval).")
    
    last_backup_str = await get_system_setting("last_backup_time")
    try:
        last_backup_ts = float(last_backup_str) if last_backup_str else 0.0
    except ValueError:
        last_backup_ts = 0.0

    now = time.time()
    if last_backup_ts > 0:
        elapsed = now - last_backup_ts
        if elapsed < BACKUP_INTERVAL:
            initial_delay = BACKUP_INTERVAL - elapsed
            logger.info(f"⏳ Last backup was {elapsed/3600:.1f}h ago. Next backup in {initial_delay/3600:.1f}h.")
        else:
            initial_delay = 300
            logger.info(f"⏳ Last backup was {elapsed/3600:.1f}h ago (overdue). Running initial backup in 5 minutes.")
    else:
        initial_delay = 300
        logger.info("⏳ No previous backup timestamp found. Running initial backup in 5 minutes.")

    await asyncio.sleep(initial_delay)
    
    while True:
        success = await create_db_backup(bot)
        if success:
            await set_system_setting("last_backup_time", str(time.time()))
            await asyncio.sleep(BACKUP_INTERVAL)
        else:
            logger.warning("⚠️ Backup failed, retrying in 1 hour...")
            await asyncio.sleep(3600)
