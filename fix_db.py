import sqlite3
import os

# Путь к файлу БД (убедись, что он правильный)
DB_NAME = "dvach_bot.db"

# Данные для новой доски
TRASH_BOARD = {
    'board_id': 'trash',
    'name': '/trash/ - Мусорка',
    'description': 'Доска без модерации для спама и тестов.'
}

def fix_database():
    if not os.path.exists(DB_NAME):
        print(f"Ошибка: Файл базы данных '{DB_NAME}' не найден.")
        return

    try:
        # Подключаемся к базе данных
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        print(f"Подключено к {DB_NAME}.")

        # Проверяем, существует ли уже запись
        cursor.execute("SELECT 1 FROM Boards WHERE board_id = ?", (TRASH_BOARD['board_id'],))
        if cursor.fetchone():
            print(f"Доска '{TRASH_BOARD['board_id']}' уже существует в базе данных. Ничего делать не нужно.")
        else:
            # Если записи нет, добавляем ее
            print(f"Добавляю доску '{TRASH_BOARD['board_id']}' в таблицу Boards...")
            cursor.execute(
                "INSERT INTO Boards (board_id, name, description, settings) VALUES (?, ?, ?, '{}')",
                (TRASH_BOARD['board_id'], TRASH_BOARD['name'], TRASH_BOARD['description'])
            )
            conn.commit()
            print("✅ Запись успешно добавлена.")

    except sqlite3.Error as e:
        print(f"⛔ Произошла ошибка SQLite: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()
            print("Соединение с БД закрыто.")

if __name__ == "__main__":
    fix_database()