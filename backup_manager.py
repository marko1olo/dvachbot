# backup_manager.py
# Выполняет создание сжатых Gzip SQL-дампов базы данных SQLite
# без зависимости от внешних утилит, используя только стандартную библиотеку Python.
import sqlite3
import gzip
import os
from datetime import datetime, timezone
import glob
DB_NAME = "dvach_bot.db"
BACKUP_DIR = "data"

# Импортируем централизованную конфигурацию
from common.config import DB_NAME

def create_gzipped_dump(db_path: str, output_dir: str) -> str | None:
    """
    Создает сжатый Gzip SQL-дамп, используя только Python, с ротацией файлов.
    Сохраняет не более 2 последних бэкапов. Универсальная ротация, обрабатывающая
    в том числе старые форматы имен файлов.

    :param db_path: Путь к файлу базы данных SQLite.
    :param output_dir: Директория для сохранения файла дампа.
    :return: Путь к созданному файлу .sql.gz или None в случае ошибки.
    """
    if not os.path.exists(db_path):
        print(f"Критическая ошибка: файл базы данных '{db_path}' не найден.")
        return None

    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    dump_filename = f"db_backup_{timestamp}.sql.gz"
    dump_filepath = os.path.join(output_dir, dump_filename)

    print(f"Начинаю создание дампа базы данных в '{dump_filepath}'...")

    try:
        with sqlite3.connect(db_path) as con:
            with gzip.open(dump_filepath, "wt", encoding="utf-8") as f:
                for line in con.iterdump():
                    f.write(f'{line}\n')
        
        print(f"Дамп базы данных успешно создан: {dump_filepath}")

        # --- НАЧАЛО ИЗМЕНЕНИЙ: Улучшенная логика ротации бэкапов ---
        try:
            # Используем более общий шаблон, чтобы находить ВСЕ файлы бэкапов,
            # включая старые файлы без временной метки (например, 'db_backup.sql.gz').
            backup_pattern = os.path.join(output_dir, "db_backup*.sql.gz")
            existing_backups = glob.glob(backup_pattern)
            
            # Сортируем файлы по времени их модификации, от старых к новым.
            # Это более надежный способ, чем сортировка по имени.
            existing_backups.sort(key=os.path.getmtime)

            # Если бэкапов больше 2, удаляем самые старые
            max_backups = 2
            if len(existing_backups) > max_backups:
                backups_to_delete = existing_backups[:-max_backups]
                print(f"Обнаружено {len(existing_backups)} бэкапов. Удаляю {len(backups_to_delete)} старых...")
                for old_backup in backups_to_delete:
                    try:
                        os.remove(old_backup)
                        print(f"  - Удален старый бэкап: {old_backup}")
                    except OSError as e:
                        print(f"  - Ошибка при удалении файла {old_backup}: {e}")
        except Exception as e:
            print(f"Ошибка во время ротации бэкапов: {e}")
        # --- КОНЕЦ ИЗМЕНЕНИЙ ---

        return dump_filepath

    except Exception as e:
        print(f"Критическая ошибка: не удалось создать дамп базы данных. Причина: {e}")
        if os.path.exists(dump_filepath):
            try:
                os.remove(dump_filepath)
            except OSError:
                pass
        return None

if __name__ == "__main__":  # pragma: no cover
    # Этот блок остается для возможности ручного тестирования скрипта.
    print("Запуск менеджера бэкапов напрямую для теста...")
    if not os.path.exists(DB_NAME):
        print(f"Файл '{DB_NAME}' не найден. Для теста создайте сначала пустую базу данных.")
        import sys
        sys.exit(1)
        
    result_path = create_gzipped_dump(DB_NAME, BACKUP_DIR)

    if result_path:
        print(f"\nУспех! Бэкап создан: {result_path}")
        import sys
        sys.exit(0)
    else:
        print(f"\nНе удалось создать бэкап.")
        import sys
        sys.exit(1)
