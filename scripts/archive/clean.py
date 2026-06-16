import asyncio
import time
import logging
import sys
import os

# Добавляем путь к корню проекта, чтобы видеть common
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from common.db_pool import create_pool, close_pool, get_pool

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("recover")

async def main():
    logger.info("🔧 Starting recovery of missing HuggingFace mirrors...")
    
    await create_pool()
    db = await get_pool()
    
    current_time = time.time()
    
    try:
        # Один мощный запрос: находит потерянные и сразу вставляет в очередь
        # INSERT OR IGNORE защищает от дубликатов в очереди
        query = """
            INSERT OR IGNORE INTO PendingHF (file_id, created_at)
            SELECT fr.file_id, ?
            FROM FileRegistry fr
            LEFT JOIN FileMirrors fm ON fr.file_id = fm.file_id AND fm.mirror_type = 'huggingface'
            WHERE fm.file_id IS NULL
        """
        
        logger.info("Executing database query... This might take a moment.")
        
        async with db.execute(query, (current_time,)) as cursor:
            # rowcount вернет количество вставленных строк
            count = cursor.rowcount
            
        await db.commit()
        
        logger.info(f"✅ Recovery Complete.")
        logger.info(f"📥 Added {count} files to HF upload queue.")
        logger.info("The hf_batcher daemon will process them automatically.")
        
    except Exception as e:
        logger.error(f"❌ Error during recovery: {e}")
    finally:
        await close_pool()

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())