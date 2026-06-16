import aiosqlite
import asyncio
import json
from common.config import DB_NAME, DB_TIMEOUT

async def migrate_database_schema():
    """
    Выполняет разовую миграцию схемы базы данных до актуального состояния.
    Скрипт является идемпотентным, его можно безопасно запускать несколько раз.
    Централизует все операции ALTER TABLE.
    """
    print("Подключение к базе данных...")
    async with aiosqlite.connect(DB_NAME, timeout=DB_TIMEOUT) as db:
        try:
            await db.execute("BEGIN;")

            # --- Миграция 1: Добавление 'last_updated_at' в таблицу Threads ---
            print("\nШаг 1: Проверка таблицы Threads...")
            try:
                await db.execute("ALTER TABLE Threads ADD COLUMN last_updated_at REAL;")
                print("  - Добавлена колонка 'last_updated_at'.")
                # Сразу заполняем новую колонку данными из created_at для существующих записей
                await db.execute("UPDATE Threads SET last_updated_at = created_at WHERE last_updated_at IS NULL;")
                print("  - Колонка 'last_updated_at' заполнена начальными значениями.")
            except aiosqlite.OperationalError as e:
                if "duplicate column name" in str(e):
                    print("  - Колонка 'last_updated_at' уже существует. Пропускаем.")
                else:
                    raise e

            # --- Миграция 2: Подготовка к миграции формата постов ---
            print("\nШаг 2: Проверка таблицы Boards для миграции постов...")
            try:
                await db.execute("ALTER TABLE Boards ADD COLUMN posts_migrated_for_files INTEGER DEFAULT 0;")
                print("  - Добавлена колонка-флаг 'posts_migrated_for_files'.")
            except aiosqlite.OperationalError as e:
                if "duplicate column name" in str(e):
                    print("  - Колонка-флаг 'posts_migrated_for_files' уже существует. Пропускаем.")
                else:
                    raise e

            # --- Миграция 3: Преобразование формата постов (если необходимо) ---
            print("\nШаг 3: Проверка необходимости миграции данных постов...")
            migration_needed = False
            await db.execute("INSERT OR IGNORE INTO Boards (board_id, name) VALUES ('b', '/b/');")
            async with db.execute("SELECT posts_migrated_for_files FROM Boards WHERE board_id = 'b'") as cursor:
                row = await cursor.fetchone()
                if row and row[0] == 0:
                    migration_needed = True

            if not migration_needed:
                print("  - Данные постов уже в актуальном формате.")
            else:
                print("  - Требуется миграция данных постов...")
                posts_to_migrate = []
                async with db.execute("SELECT post_num, content FROM Posts WHERE json_extract(content, '$.type') = 'image'") as cursor:
                    async for row_data in cursor:
                        posts_to_migrate.append(row_data)

                if not posts_to_migrate:
                    print("    - Постов для преобразования не найдено.")
                else:
                    print(f"    - Найдено {len(posts_to_migrate)} постов для преобразования.")
                    updated_posts = []
                    for post_num, content_json in posts_to_migrate:
                        try:
                            content_data = json.loads(content_json)
                            new_content = {
                                "type": "files",
                                "text": content_data.get("text", ""),
                                "files": [{
                                    "type": "image",
                                    "original_file_id": content_data.get("image_data", {}).get("original_file_id"),
                                    "thumbnail_file_id": content_data.get("image_data", {}).get("thumbnail_file_id")
                                }]
                            }
                            updated_posts.append((json.dumps(new_content), post_num))
                        except (json.JSONDecodeError, TypeError):
                            print(f"    - Предупреждение: не удалось обработать JSON для поста #{post_num}. Пропущено.")
                            continue
                    
                    if updated_posts:
                        await db.executemany("UPDATE Posts SET content = ? WHERE post_num = ?", updated_posts)
                        print(f"    - Успешно обновлено {len(updated_posts)} постов.")

                await db.execute("UPDATE Boards SET posts_migrated_for_files = 1 WHERE board_id = 'b';")
                print("  - Установлен флаг завершения миграции данных постов.")

            await db.commit()
            print("\n[РЕЗУЛЬТАТ] Миграция схемы базы данных успешно завершена!")

        except Exception as e:
            print(f"\n[ОШИБКА] Произошла ошибка во время миграции: {e}")
            print("  - Выполняется откат изменений...")
            await db.rollback()
            print("  - Изменения отменены.")

if __name__ == "__main__":
    print("Запуск скрипта миграции схемы базы данных...")
    asyncio.run(migrate_database_schema())