import asyncio
import aiosqlite
import os
import time

DB_NAME = "dvach_bot.db"

async def requeue_files():
    if not os.path.exists(DB_NAME):
        print(f"❌ База данных {DB_NAME} не найдена!")
        return

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        now = time.time()

        print("🚀 Запуск процесса перепостановки в очереди...")

        # 1. Очередь HuggingFace
        # Добавляем файлы с тегами, которых еще нет в PendingHF и у которых нет зеркала HF
        hf_query = """
            INSERT OR IGNORE INTO PendingHF (file_id, created_at)
            SELECT file_id, ? 
            FROM FileRegistry 
            WHERE tags IS NOT NULL 
            AND tags != ''
            AND file_id NOT IN (SELECT file_id FROM FileMirrors WHERE mirror_type = 'huggingface')
        """
        cursor_hf = await db.execute(hf_query, (now,))
        print(f"✅ HuggingFace: добавлено {cursor_hf.rowcount} новых задач.")

        # 2. Очередь Catbox
        # Добавляем файлы с тегами в MirrorQueue
        cb_query = """
            INSERT OR IGNORE INTO MirrorQueue (file_id, mirror_type, next_run_at, attempts)
            SELECT file_id, 'catbox', ?, 0
            FROM FileRegistry 
            WHERE tags IS NOT NULL 
            AND tags != ''
            AND file_id NOT IN (SELECT file_id FROM FileMirrors WHERE mirror_type = 'catbox')
        """
        cursor_cb = await db.execute(cb_query, (now,))
        print(f"✅ Catbox: добавлено {cursor_cb.rowcount} новых задач.")

        await db.commit()
        
        # Результирующая статистика
        async with db.execute("SELECT COUNT(*) FROM PendingHF") as c:
            count_hf = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM MirrorQueue WHERE mirror_type = 'catbox'") as c:
            count_cb = (await c.fetchone())[0]

        print(f"\n📊 ИТОГО В ОЧЕРЕДЯХ:\n- HuggingFace: {count_hf}\n- Catbox: {count_cb}")
        print("\n💡 Воркеры подхватят задачи автоматически.")

if __name__ == "__main__":
    asyncio.run(requeue_files())