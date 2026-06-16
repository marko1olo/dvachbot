import sqlite3
import time
import os

DB_NAME = "dvach_bot.db"
TARGET_THREAD = 278266

def run_fix():
    if not os.path.exists(DB_NAME):
        print(f"❌ Ошибка: Файл {DB_NAME} не найден!")
        return

    print(f"🚀 Начинаю восстановление базы данных...")
    
    conn = None
    try:
        # Устанавливаем большой таймаут на случай, если кто-то еще держит базу
        conn = sqlite3.connect(DB_NAME, timeout=30.0)
        cursor = conn.cursor()

        # 1. Включаем WAL для стабильности
        cursor.execute("PRAGMA journal_mode=WAL;")
        
        # 2. Лечим тред #278266
        print(f"🛠️ Обновляю тред #{TARGET_THREAD}...")
        now = time.time()
        
        # Обновляем время последнего ответа, чтобы вытолкнуть тред наверх
        cursor.execute(
            "UPDATE Threads SET last_updated_at = ?, stream = 'ru', is_archived = 0 WHERE thread_num = ?", 
            (now, TARGET_THREAD)
        )
        
        # Проверяем ОП-пост
        cursor.execute(
            "UPDATE Posts SET stream = 'ru', is_shadow = 0 WHERE post_num = ?", 
            (TARGET_THREAD,)
        )

        # 3. Глубокое обслуживание индексов
        print("🔍 Пересобираю индексы (это может занять время)...")
        cursor.execute("REINDEX Threads;")
        cursor.execute("REINDEX Posts;")
        
        # 4. Оптимизация FTS (поиска)
        print("⚡ Оптимизирую поисковые таблицы...")
        try:
            cursor.execute("INSERT INTO PostsFTS(PostsFTS) VALUES('optimize');")
            cursor.execute("INSERT INTO FileTagsFTS(FileTagsFTS) VALUES('optimize');")
        except sqlite3.OperationalError as e:
            print(f"⚠️ Пропущена оптимизация FTS (не критично): {e}")

        # 5. Финальная очистка
        print("🧹 Выполняю PRAGMA optimize...")
        cursor.execute("PRAGMA optimize;")
        
        conn.commit()
        print(f"✅ УСПЕХ: Тред #{TARGET_THREAD} восстановлен. Индексы починены.")

    except sqlite3.OperationalError as e:
        print(f"⛔ ОШИБКА: База данных заблокирована! Закройте все программы, использующие её: {e}")
    except Exception as e:
        print(f"💥 Непредвиденная ошибка: {e}")
    finally:
        if conn:
            conn.close()
            print("🔌 Соединение закрыто.")

if __name__ == "__main__":
    run_fix()