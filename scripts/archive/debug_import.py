# debug_import.py
import asyncio
import aiosqlite
import json
import os

DB_NAME = "dvach_bot.db"
IMPORT_DIR = "data_export"
ERROR_LOG_FILE = "import_errors.log"


def _read_json_file(path: str):
    with open(path, 'r', encoding='utf-8') as file:
        return json.load(file)


def _append_import_error(path: str, error: Exception, post: dict) -> None:
    with open(path, 'a', encoding='utf-8') as file:
        file.write(f"--- ОШИБКА: {error} ---\n")
        file.write(json.dumps(post, ensure_ascii=False, indent=2))
        file.write("\n\n")


async def debug_import():
    if not os.path.exists(DB_NAME):
        print(f"⛔ Ошибка: Файл базы данных '{DB_NAME}' не найден. Сначала запустите create_new_db.py.")
        return

    if os.path.exists(ERROR_LOG_FILE):
        os.remove(ERROR_LOG_FILE)
        print(f"Удален старый лог-файл: {ERROR_LOG_FILE}")

    print(f"--- Начало ДИАГНОСТИЧЕСКОГО импорта ---")
    print(f"Проблемные посты будут записаны в файл: {ERROR_LOG_FILE}")

    db = None
    try:
        db = await aiosqlite.connect(DB_NAME)
        await db.execute("PRAGMA foreign_keys = ON;")

        # --- Шаг 1: Импорт безопасных таблиц ---
        safe_tables = ["Boards", "Users"]
        async with db.execute("BEGIN;"):
            for table_name in safe_tables:
                import_file_path = os.path.join(IMPORT_DIR, f"{table_name}.json")
                if not os.path.exists(import_file_path): continue
                
                data_to_import = await asyncio.to_thread(_read_json_file, import_file_path)
                if not data_to_import: continue

                print(f"Импортирую '{table_name}'...")
                columns = data_to_import[0].keys()
                query = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({', '.join(['?'] * len(columns))});"
                values = [tuple(item.get(col) for col in columns) for item in data_to_import]
                await db.executemany(query, values)
                print(f" -> ✅ Готово: {len(values)} записей.")
        await db.commit()

        # --- Шаг 2: Диагностический импорт таблицы Posts ---
        print("\nНачинаю построчный импорт 'Posts' для выявления ошибок...")
        posts_file = os.path.join(IMPORT_DIR, "Posts.json")
        all_posts_data = await asyncio.to_thread(_read_json_file, posts_file)
        all_posts_data.sort(key=lambda x: x['post_num'])
        
        successful_imports = 0
        failed_imports = 0
        
        columns = all_posts_data[0].keys()
        query = f"INSERT INTO Posts ({', '.join(columns)}) VALUES ({', '.join(['?'] * len(columns))});"

        chunk_size = 500
        for i in range(0, len(all_posts_data), chunk_size):
            chunk = all_posts_data[i:i + chunk_size]
            values = [tuple(post.get(col) for col in columns) for post in chunk]

            try:
                await db.execute("BEGIN;")
                await db.executemany(query, values)
                await db.commit()
                successful_imports += len(values)
            except aiosqlite.IntegrityError:
                await db.rollback()
                # Если чанк упал из-за дубля (или другой IntegrityError),
                # откатываемся к построчной вставке для этого чанка,
                # чтобы залогировать конкретную ошибку
                for post, val in zip(chunk, values):
                    try:
                        await db.execute(query, val)
                        await db.commit()
                        successful_imports += 1
                    except aiosqlite.IntegrityError as e:
                        failed_imports += 1
                        await asyncio.to_thread(_append_import_error, ERROR_LOG_FILE, e, post)
                        await db.rollback()

        print(f"\n--- Диагностика 'Posts' завершена ---")
        print(f" -> ✅ Успешно импортировано: {successful_imports}")
        print(f" -> ⛔ Сбойных записей: {failed_imports}")
        if failed_imports > 0:
            print(f" -> 📄 Детали сбоев записаны в файл {ERROR_LOG_FILE}")

        # --- Шаг 3: Импорт оставшихся таблиц ---
        remaining_tables = ["Threads", "Mutes", "PostCopies"]
        print("\nНачинаю импорт оставшихся таблиц...")
        async with db.execute("BEGIN;"):
            for table_name in remaining_tables:
                import_file_path = os.path.join(IMPORT_DIR, f"{table_name}.json")
                if not os.path.exists(import_file_path): continue
                data_to_import = await asyncio.to_thread(_read_json_file, import_file_path)
                if not data_to_import: continue
                
                print(f"Импортирую '{table_name}'...")
                columns = data_to_import[0].keys()
                query = f"INSERT OR IGNORE INTO {table_name} ({', '.join(columns)}) VALUES ({', '.join(['?'] * len(columns))});"
                values = [tuple(item.get(col) for col in columns) for item in data_to_import]
                await db.executemany(query, values)
                print(f" -> ✅ Готово: {len(values)} записей.")

        await db.commit()
        print("\n--- ✅ Диагностический импорт завершен. ---")

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\n⛔ КРИТИЧЕСКАЯ НЕПРЕДВИДЕННАЯ ОШИБКА: {e}")
    finally:
        if db:
            await db.close()

if __name__ == "__main__":
    asyncio.run(debug_import())
