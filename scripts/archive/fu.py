import asyncio
import aiosqlite
import os

DB_NAME = "dvach_bot.db"

async def kill_zombies():
    if not os.path.exists(DB_NAME):
        print(f"❌ ОШИБКА: База данных '{DB_NAME}' не найдена!")
        return

    async with aiosqlite.connect(DB_NAME) as db:
        # Паттерны: AgAC (фото), BQAC (файлы/видео), CQAC (аудио)
        patterns = ['AgAC%', 'BQAC%', 'CQAC%']
        
        where_clause = " OR ".join(["file_id LIKE ?"] * len(patterns))

        # Чистим MirrorQueue (Catbox)
        await db.execute(f"DELETE FROM MirrorQueue WHERE {where_clause}", patterns)
        # Чистим PendingHF (HuggingFace)
        await db.execute(f"DELETE FROM PendingHF WHERE {where_clause}", patterns)
        
        await db.commit()
        print("✅ Все зомби-задачи (AgAC, BQAC, CQAC) удалены из очередей.")

if __name__ == "__main__":
    asyncio.run(kill_zombies())