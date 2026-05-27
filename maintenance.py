# Файл: maintenance.py
import sqlite3
import os
from common.config import DB_NAME

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
        with sqlite3.connect(DB_NAME) as con:
            print("⏳ Запуск VACUUM для сжатия файла базы данных...")
            con.execute("VACUUM;")
            print("✅ VACUUM успешно завершен.")

            print("⏳ Запуск ANALYZE для оптимизации будущих запросов...")
            con.execute("ANALYZE;")
            print("✅ ANALYZE успешно завершен.")
        
        print("\nОбслуживание базы данных успешно завершено!")

    except Exception as e:
        print(f"⛔ КРИТИЧЕСКАЯ ОШИБКА во время обслуживания: {e}")

if __name__ == "__main__":
    print("--- Скрипт обслуживания базы данных ---")
    print("!!! ВНИМАНИЕ: Перед запуском убедитесь, что и бот, и сайт ПОЛНОСТЬЮ ОСТАНОВЛЕНЫ. !!!")
    
    answer = input("Продолжить? (y/n): ").lower()
    
    if answer == 'y':
        run_maintenance()
    else:
        print("Операция отменена.")