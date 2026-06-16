import sqlite3
import os

DB_NAME = "dvach_bot.db"

def check_triggers():
    if not os.path.exists(DB_NAME):
        print(f"⛔ Ошибка: Файл базы данных '{DB_NAME}' не найден в текущей директории.")
        return

    print(f"--- Анализ триггеров в файле {DB_NAME} ---")
    try:
        con = sqlite3.connect(DB_NAME)
        cursor = con.cursor()
        
        cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger';")
        triggers = cursor.fetchall()
        
        if not triggers:
            print("\n✅ Триггеры не найдены в базе данных.")
        else:
            print(f"\n✅ Найдено триггеров: {len(triggers)}\n")
            for name, sql in triggers:
                print(f"--- Триггер: {name} ---")
                print(sql)
                print("-" * (len(name) + 16) + "\n")
                
        con.close()
        print("--- Анализ завершен. ---")

    except Exception as e:
        print(f"⛔ Произошла ошибка при анализе базы данных: {e}")

if __name__ == "__main__":
    check_triggers()