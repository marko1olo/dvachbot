import sqlite3

DB_NAME = "dvach_bot.db"

print("🔧 Восстанавливаю поисковый индекс...")
con = sqlite3.connect(DB_NAME)
cur = con.cursor()

try:
    # Эта магическая команда заставляет SQLite заново прочитать все посты
    # и заполнить таблицу поиска PostsFTS
    cur.execute("INSERT INTO PostsFTS(PostsFTS) VALUES('rebuild');")
    con.commit()
    print("✅ Готово! Поиск по сайту снова работает.")
except Exception as e:
    print(f"❌ Ошибка: {e}")
finally:
    con.close()