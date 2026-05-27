import asyncio
import aiosqlite
import json

DB_NAME = "dvach_bot.db"

async def migrate():
    """
    Выполняет безопасную миграцию схемы базы данных, добавляя недостающие
    таблицы, индексы и триггеры без удаления существующих данных.
    """
    print(f"--- Начало миграции базы данных {DB_NAME} ---")
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            # --- Шаг 1: Создание недостающих таблиц ---
            print("Шаг 1: Создание недостающих таблиц...")
            
            # Таблица-очередь для трансляции
            await db.execute("""
            CREATE TABLE IF NOT EXISTS BroadcastQueue (
                post_num INTEGER PRIMARY KEY,
                created_at REAL NOT NULL,
                FOREIGN KEY (post_num) REFERENCES Posts(post_num) ON DELETE CASCADE
            );
            """)
            
            # Таблица-очередь для уведомлений
            await db.execute("""
            CREATE TABLE IF NOT EXISTS NotificationQueue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipient_id INTEGER NOT NULL,
                source_post_num INTEGER NOT NULL,
                reply_post_num INTEGER NOT NULL,
                FOREIGN KEY (source_post_num) REFERENCES Posts(post_num) ON DELETE CASCADE,
                FOREIGN KEY (reply_post_num) REFERENCES Posts(post_num) ON DELETE CASCADE
            );
            """)

            # Виртуальная таблица для полнотекстового поиска
            await db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS PostsFTS USING fts5(
                content,
                content='Posts',
                content_rowid='post_num',
                tokenize='porter unicode61'
            );
            """)
            print(" -> Таблицы успешно созданы (если не существовали).")

            # --- Шаг 2: Создание недостающих индексов и триггеров ---
            print("Шаг 2: Создание недостающих индексов и триггеров...")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_broadcastqueue_created_at ON BroadcastQueue(created_at);")

            await db.execute("""
            CREATE TRIGGER IF NOT EXISTS posts_after_insert AFTER INSERT ON Posts
            BEGIN
                INSERT INTO PostsFTS(rowid, content) VALUES (new.post_num, new.content);
            END;
            """)
            await db.execute("""
            CREATE TRIGGER IF NOT EXISTS posts_after_delete AFTER DELETE ON Posts
            BEGIN
                INSERT INTO PostsFTS(PostsFTS, rowid, content) VALUES ('delete', old.post_num, old.content);
            END;
            """)
            await db.execute("""
            CREATE TRIGGER IF NOT EXISTS posts_after_update AFTER UPDATE ON Posts
            BEGIN
                INSERT INTO PostsFTS(PostsFTS, rowid, content) VALUES ('delete', old.post_num, old.content);
                INSERT INTO PostsFTS(rowid, content) VALUES (new.post_num, new.content);
            END;
            """)
            print(" -> Индексы и триггеры успешно созданы (если не существовали).")

            # --- Шаг 3: Наполнение FTS-таблицы существующими данными ---
            print("Шаг 3: Проверка и наполнение поискового индекса (FTS)...")
            
            # Проверяем, пуст ли индекс
            cursor = await db.execute("SELECT count(*) FROM PostsFTS;")
            count = (await cursor.fetchone())[0]
            
            if count == 0:
                print(" -> Поисковый индекс пуст. Начинаю полное индексирование...")
                # Специальная команда FTS5 для перестройки индекса из связанной таблицы
                await db.execute("INSERT INTO PostsFTS(PostsFTS) VALUES('rebuild');")
                await db.commit()
                print(" -> Полное индексирование завершено.")
            else:
                print(" -> Поисковый индекс уже содержит данные. Пропуск наполнения.")

            await db.commit()

        print("\n--- Миграция успешно завершена! ---")

    except Exception as e:
        print(f"\n⛔ КРИТИЧЕСКАЯ ОШИБКА во время миграции: {e}")
        print(" -> Никакие изменения не были сохранены.")

if __name__ == "__main__":
    # Остановите вашего бота перед запуском этого скрипта!
    print("ВНИМАНИЕ: Перед запуском этого скрипта убедитесь, что ваш Telegram-бот остановлен.")
    confirm = input("Продолжить? (y/n): ")
    if confirm.lower() == 'y':
        asyncio.run(migrate())