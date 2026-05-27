# cleanup_db_aggressive.py
import sqlite3
import os
import sys

# --- НАСТРОЙКИ ---
# Имя вашей основной базы данных
DB_PATH = 'dvach_bot.db'
# Сколько последних постов оставить в базе
POST_LIMIT = 5000
# --- КОНЕЦ НАСТРОЕК ---

def cleanup_database_aggressive():
    """
    Выполняет агрессивную очистку базы данных:
    1. Удаляет "орфанные" записи из PostCopies.
    2. Удаляет старые посты сверх лимита POST_LIMIT.
    3. Сжимает файл БД с помощью VACUUM.
    """
    if not os.path.exists(DB_PATH):
        print(f"ОШИБКА: Файл базы данных не найден по пути: {DB_PATH}")
        sys.exit(1)

    print(f"Подключение к базе данных: {DB_PATH}...")
    try:
        with sqlite3.connect(DB_PATH, timeout=60.0) as con:
            print("Соединение установлено. Включаю режим WAL для безопасности...")
            con.execute("PRAGMA journal_mode=WAL;")
            con.execute("PRAGMA foreign_keys = ON;")

            # --- ЭТАП 1: Удаление "орфанных" записей из PostCopies ---
            print("\n--- ЭТАП 1: Очистка 'орфанных' копий постов (PostCopies) ---")
            
            # Считаем количество орфанных записей
            orphan_query = """
                SELECT COUNT(*) FROM PostCopies
                WHERE post_num NOT IN (SELECT post_num FROM Posts);
            """
            orphan_count = con.execute(orphan_query).fetchone()[0]
            print(f"Найдено 'орфанных' записей в PostCopies: {orphan_count}")

            if orphan_count > 0:
                confirm_orphan = input(f"Удалить {orphan_count} 'орфанных' записей? (yes/no): ")
                if confirm_orphan.lower() == 'yes':
                    print("Удаление 'орфанных' записей (это может занять несколько минут)...")
                    # Используем DELETE с подзапросом
                    delete_orphan_query = """
                        DELETE FROM PostCopies
                        WHERE post_num NOT IN (SELECT post_num FROM Posts);
                    """
                    cursor = con.execute(delete_orphan_query)
                    con.commit()
                    print(f"Удалено {cursor.rowcount} 'орфанных' записей из PostCopies.")
                else:
                    print("Удаление 'орфанных' записей отменено.")
            else:
                print("Орфанные записи в PostCopies не найдены.")

            # --- ЭТАП 2: Удаление старых постов ---
            print("\n--- ЭТАП 2: Удаление старых постов ---")
            total_count = con.execute("SELECT COUNT(*) FROM Posts").fetchone()[0]
            print(f"Найдено постов в базе: {total_count}")

            if total_count > POST_LIMIT:
                to_delete_count = total_count - POST_LIMIT
                print(f"Планируется к удалению: {to_delete_count} самых старых постов.")
                
                confirm_posts = input("Удалить старые посты? (yes/no): ")
                if confirm_posts.lower() == 'yes':
                    print("Определение порога для удаления...")
                    threshold_post_num = con.execute(
                        f"SELECT post_num FROM Posts ORDER BY post_num DESC LIMIT 1 OFFSET {POST_LIMIT - 1}"
                    ).fetchone()
                    
                    if threshold_post_num:
                        threshold_id = threshold_post_num[0]
                        print(f"Все посты с ID меньше {threshold_id} будут удалены.")
                        
                        print("Запуск процесса удаления постов (это может занять время)...")
                        delete_posts_query = "DELETE FROM Posts WHERE post_num < ?"
                        cursor = con.execute(delete_posts_query, (threshold_id,))
                        con.commit()
                        print(f"Удалено {cursor.rowcount} старых постов. Связанные данные удалены через CASCADE.")
                    else:
                        print("Не удалось определить порог, удаление постов пропущено.")
                else:
                    print("Удаление старых постов отменено.")
            else:
                print("Количество постов не превышает лимит. Очистка не требуется.")

            # --- ЭТАП 3: Сжатие файла БД ---
            print("\n--- ЭТАП 3: Сжатие файла базы данных ---")
            confirm_vacuum = input("Выполнить VACUUM для уменьшения размера файла? (yes/no): ")
            if confirm_vacuum.lower() == 'yes':
                print("Запуск VACUUM (это может занять очень много времени)...")
                con.execute("VACUUM;")
                con.commit()
                print("VACUUM успешно завершен.")
            else:
                print("VACUUM пропущен.")

    except sqlite3.Error as e:
        print(f"ОШИБКА SQLITE: {e}")
    except Exception as e:
        print(f"НЕПРЕДВИДЕННАЯ ОШИБКА: {e}")

if __name__ == "__main__":
    cleanup_database_aggressive()
    print("\nСкрипт завершил работу.")