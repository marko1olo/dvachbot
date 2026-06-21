import sqlite3
import json
import time
import re
from collections import defaultdict

# --- НАСТРОЙКИ ---
# Убедитесь, что имя файла базы данных правильное
DB_NAME = "dvach_bot.db"
# На какое зеркало ставить в очередь (catbox - самый частый вариант)
DEFAULT_MIRROR_TYPE = "catbox"
# -----------------

def find_and_queue_posts_without_mirrors(conn):
    """
    Находит все файлы в постах, у которых нет зеркал, и добавляет их в очередь.
    """
    print("\n--- 1. Проверка файлов без зеркал ---")
    cursor = conn.cursor()

    # Шаг 1: Получаем ID всех файлов, которые уже имеют зеркала или стоят в очереди.
    # Это нужно для эффективности, чтобы не проверять их в большом запросе.
    processed_files = set()
    cursor.execute("SELECT file_id FROM FileMirrors")
    for row in cursor:
        processed_files.add(row[0])
    
    cursor.execute("SELECT file_id FROM MirrorQueue")
    for row in cursor:
        processed_files.add(row[0])

    print(f"[*] Найдено {len(processed_files)} файлов, которые уже обработаны или в очереди.")

    # Шаг 2: Итерируемся по всем постам и извлекаем из их JSON-контента ID файлов.
    files_to_check = set()
    cursor.execute("SELECT content FROM Posts WHERE json_valid(content) AND content LIKE '%\"files\"%'")
    
    total_posts_with_files = 0
    for row in cursor:
        total_posts_with_files += 1
        try:
            content = json.loads(row[0])
            if 'files' in content and isinstance(content['files'], list):
                for file_info in content['files']:
                    if isinstance(file_info, dict) and 'original_file_id' in file_info:
                        files_to_check.add(file_info['original_file_id'])
        except (json.JSONDecodeError, TypeError):
            continue
    
    print(f"[*] Найдено {len(files_to_check)} уникальных файлов в {total_posts_with_files} постах.")

    # Шаг 3: Находим разницу - файлы, которые есть в постах, но не в зеркалах/очереди.
    missing_mirror_files = files_to_check - processed_files

    if not missing_mirror_files:
        print("✅ Отлично! Все файлы либо имеют зеркала, либо уже стоят в очереди.")
        return

    print(f"⚠️ Найдено {len(missing_mirror_files)} файлов без зеркал. Добавляем их в очередь...")

    # Шаг 4: Добавляем найденные файлы в очередь на создание зеркал.
    tasks_to_add = []
    current_time = time.time()
    for file_id in missing_mirror_files:
        # (file_id, mirror_type, attempts, next_run_at)
        tasks_to_add.append((file_id, DEFAULT_MIRROR_TYPE, 0, current_time))

    try:
        cursor.executemany(
            """
            INSERT INTO MirrorQueue (file_id, mirror_type, attempts, next_run_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(file_id, mirror_type) DO NOTHING
            """,
            tasks_to_add
        )
        conn.commit()
        print(f"✅ Успешно добавлено {len(tasks_to_add)} задач в MirrorQueue.")
    except Exception as e:
        print(f"❌ Ошибка при добавлении задач в очередь: {e}")


def find_and_report_orphans(conn):
    """
    Ищет "сиротские" записи в базе данных и выводит отчет.
    """
    print("\n--- 2. Проверка на 'сиротские' записи ---")
    cursor = conn.cursor()
    total_orphans = 0

    # Список проверок: (Название проверки, SQL-запрос для поиска сирот)
    orphan_checks = [
        (
            "Посты, ссылающиеся на несуществующие треды",
            "SELECT post_num FROM Posts WHERE thread_id IS NOT NULL AND thread_id NOT IN (SELECT thread_id FROM Threads)"
        ),
        (
            "Треды, у которых удален ОП-пост",
            "SELECT thread_id FROM Threads WHERE thread_id NOT IN (SELECT post_num FROM Posts)"
        ),
        (
            "Копии постов (PostCopies), ссылающиеся на удаленные посты",
            "SELECT post_num FROM PostCopies WHERE post_num NOT IN (SELECT post_num FROM Posts)"
        ),
        (
            "Копии в каналах (ChannelCopies), ссылающиеся на удаленные посты",
            "SELECT post_num FROM ChannelCopies WHERE post_num NOT IN (SELECT post_num FROM Posts)"
        ),
        (
            "Жалобы (Reports), ссылающиеся на удаленные посты",
            "SELECT post_num FROM Reports WHERE post_num NOT IN (SELECT post_num FROM Posts)"
        ),
        (
            "Голоса в опросах (PollVotes), ссылающиеся на удаленные посты",
            "SELECT post_num FROM PollVotes WHERE post_num NOT IN (SELECT post_num FROM Posts)"
        ),
        (
            "Уведомления (NotificationQueue), ссылающиеся на удаленные посты (source)",
            "SELECT source_post_num FROM NotificationQueue WHERE source_post_num NOT IN (SELECT post_num FROM Posts)"
        ),
        (
            "Уведомления (NotificationQueue), ссылающиеся на удаленные посты (reply)",
            "SELECT reply_post_num FROM NotificationQueue WHERE reply_post_num NOT IN (SELECT post_num FROM Posts)"
        )
    ]

    for description, query in orphan_checks:
        try:
            cursor.execute(query)
            orphans = cursor.fetchall()
            if orphans:
                count = len(orphans)
                total_orphans += count
                print(f"⚠️ Найдено: {description} - {count} шт.")
                # Показываем несколько примеров для диагностики
                sample_ids = [str(o[0]) for o in orphans[:5]]
                print(f"   Примеры ID: {', '.join(sample_ids)}")
            else:
                print(f"✅ {description} - сирот не найдено.")
        except sqlite3.OperationalError as e:
            print(f"❌ Ошибка при проверке '{description}': {e}. Возможно, таблицы еще не существует.")

    if total_orphans == 0:
        print("\n✅ Отлично! Сиротских записей в основных таблицах не обнаружено.")
    else:
        print(f"\n- Итого найдено {total_orphans} сиротских записей. Рекомендуется ручная очистка.")


def main():
    """
    Основная функция для запуска проверок.
    """
    conn = None
    try:
        # Подключаемся к базе данных
        conn = sqlite3.connect(f'file:{DB_NAME}?mode=ro', uri=True)
        print(f"Успешно подключено к '{DB_NAME}' в режиме только для чтения для анализа.")
        
        # Запускаем отчет по сиротам (только чтение)
        find_and_report_orphans(conn)
        conn.close()

        # Для добавления в очередь нужно подключение на запись/чтение
        conn = sqlite3.connect(DB_NAME, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL;") # Включаем WAL для уменьшения блокировок
        
        # Запускаем поиск и добавление в очередь
        find_and_queue_posts_without_mirrors(conn)

        print("\n--- Проверка завершена ---")

    except sqlite3.Error as e:
        print(f"❌ Критическая ошибка при работе с базой данных: {e}")
    finally:
        if conn:
            conn.close()
            print("Соединение с базой данных закрыто.")

if __name__ == "__main__":
    main()