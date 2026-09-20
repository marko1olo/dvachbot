import contextlib
# Файл: maintenance.py
import os
import sqlite3
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from common.config import DB_NAME



def clean_old_postcopies(con, retention_days: int = 3):
    """
    Удаляет устаревшие связки доставки PostCopies перед VACUUM,
    чтобы освобожденные страницы были возвращены операционной системе.
    """
    try:
        cutoff_ts = time.time() - (retention_days * 86400)
        cur = con.cursor()
        cur.execute("SELECT MIN(post_num) FROM Posts WHERE timestamp >= ?", (cutoff_ts,))
        row = cur.fetchone()
        if row and isinstance(row[0], (int, float)):
            thresh = int(row[0])
            cur.execute("DELETE FROM PostCopies WHERE post_num < ?", (thresh,))
            con.commit()
            print(f"🗑️ Удалены устаревшие связки PostCopies (до поста #{thresh}).")
    except Exception as ex:
        print(f"⚠️ Пропуск очистки PostCopies: {ex}")


def run_maintenance():
    """
    Выполняет VACUUM и ANALYZE для базы данных.
    ВАЖНО: Запускать только при остановленных боте и сайте!
    """
    if not os.path.exists(DB_NAME):
        print(f"Ошибка: Файл базы данных не найден по пути: {DB_NAME}")
        return

    print(f"Подключение к базе данных: {DB_NAME}")
    try:
        with contextlib.closing(sqlite3.connect(DB_NAME, timeout=15.0)) as con:
            try: con.execute('PRAGMA journal_mode=WAL')
            except Exception: pass
            try: con.execute('PRAGMA synchronous=NORMAL')
            except Exception: pass
            try: con.execute('PRAGMA busy_timeout=120000')
            except Exception: pass
            try: con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            except Exception: pass

            clean_old_postcopies(con, retention_days=3)

            print("⏳ Запуск VACUUM для сжатия файла базы данных...")
            con.execute("VACUUM;")
            print("✅ VACUUM успешно завершен.")

            print("⏳ Запуск ANALYZE для оптимизации будущих запросов...")
            con.execute("ANALYZE;")
            print("✅ ANALYZE успешно завершен.")

            try: con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            except Exception: pass
        
        print("\nОбслуживание базы данных успешно завершено!")

    except Exception as e:
        print(f"⛔ КРИТИЧЕСКАЯ ОШИБКА во время обслуживания: {e}")

if __name__ == "__main__":
    print("--- Скрипт обслуживания базы данных ---")
    print("!!! ВНИМАНИЕ: Перед запуском убедитесь, что и бот, и сайт ПОЛНОСТЬЮ ОСТАНОВЛЕНЫ. !!!")
    
    if "-y" in sys.argv or "--yes" in sys.argv:
        run_maintenance()
    else:
        answer = input("Продолжить? (y/n): ").lower()
        if answer == 'y':
            run_maintenance()
        else:
            print("Операция отменена.")