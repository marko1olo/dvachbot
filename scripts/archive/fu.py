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
        
        for p in patterns:
            # Чистим MirrorQueue (Catbox)
            await db.execute("DELETE FROM MirrorQueue WHERE file_id LIKE ?", (p,))
            # Чистим PendingHF (HuggingFace)
            await db.execute("DELETE FROM PendingHF WHERE file_id LIKE ?", (p,))
        
        await db.commit()
        print("✅ Все зомби-задачи (AgAC, BQAC, CQAC) удалены из очередей.")

if __name__ == "__main__":
    asyncio.run(kill_zombies())