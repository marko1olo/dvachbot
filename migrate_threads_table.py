import asyncio
import aiosqlite

DB_NAME = "dvach_bot.db"

async def migrate():
    print("--- Начало миграции: создание таблицы Threads ---")
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("""
            CREATE TABLE IF NOT EXISTS Threads (
                thread_id INTEGER PRIMARY KEY,
                is_archived BOOLEAN NOT NULL DEFAULT 0,
                FOREIGN KEY (thread_id) REFERENCES Posts(post_num) ON DELETE CASCADE
            );
            """)
            print("✅ Таблица Threads успешно создана (если не существовала).")
            await db.commit()
    except Exception as e:
        print(f"⛔ КРИТИЧЕСКАЯ ОШИБКА во время миграции: {e}")

if __name__ == "__main__":
    asyncio.run(migrate())