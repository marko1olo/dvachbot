import sqlite3
import os
import re
import sys

# === НАСТРОЙКИ ===
SQL_FILE = "backup.sql"
DB_FILE = "dvach_bot.db"
CLEAN_SQL_FILE = "backup_clean_temp.sql"
# =================

def restore_db():
    print(f"🔧 Запуск восстановления БД '{DB_FILE}'...")

    if not os.path.exists(SQL_FILE):
        print(f"❌ Файл {SQL_FILE} не найден!")
        return

    # 1. Удаляем старую базу
    if os.path.exists(DB_FILE):
        try:
            os.remove(DB_FILE)
            print(f"🗑️ Старый файл {DB_FILE} удален.")
        except PermissionError:
            print("❌ ОШИБКА: Закрой все программы, использующие базу!")
            return

    # 2. Читаем и чистим SQL (используем utf-8-sig для удаления BOM)
    print(f"📖 Читаю и лечу файл {SQL_FILE}...")
    try:
        with open(SQL_FILE, 'r', encoding='utf-8-sig', errors='replace') as f:
            content = f.read()
    except Exception as e:
        print(f"❌ Ошибка чтения: {e}")
        return

    # Убираем создание PostsFTS (оно вызывает конфликт с триггерами)
    # Ищем любые вариации CREATE VIRTUAL TABLE ... PostsFTS
    pattern_fts = r'CREATE\s+VIRTUAL\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["`]?PostsFTS["`]?\s+USING\s+fts5\s*\(.*?\);'
    content = re.sub(pattern_fts, '', content, flags=re.IGNORECASE | re.DOTALL)
    
    # Убираем транзакции из файла (мы будем управлять ими сами)
    content = content.replace('BEGIN TRANSACTION;', '').replace('COMMIT;', '')

    # 3. Создаем новую базу и таблицу FTS вручную
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    
    # Настройки скорости
    cur.execute("PRAGMA journal_mode = WAL;")
    cur.execute("PRAGMA synchronous = OFF;") 
    cur.execute("PRAGMA foreign_keys = OFF;") # Важно!

    print("🔧 Создаю структуру FTS вручную...")
    cur.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS PostsFTS USING fts5(
            content,
            content='Posts',
            content_rowid='post_num'
        );
    """)

    # 4. Разбиваем на команды и исполняем по одной
    # Это медленнее, но позволит пропустить ту самую битую строку с "{"
    print("🚀 Начинаю заливку данных (построчно)...")
    
    # Разбиваем по точке с запятой, но аккуратно
    # Примитивная разбивка, может сбоить на ; внутри текста, но для восстановления пойдет
    commands = content.split(';\n') 
    
    total = len(commands)
    success = 0
    errors = 0

    cur.execute("BEGIN TRANSACTION;")
    
    for i, cmd in enumerate(commands):
        if not cmd.strip():
            continue
            
        try:
            # Пробуем выполнить команду
            cur.execute(cmd)
            success += 1
        except sqlite3.Error as e:
            # Если ошибка — игнорируем именно эту строку, но не падаем
            err_msg = str(e)
            # Игнорируем ошибки "таблица уже существует", это нормально при восстановлении
            if "already exists" not in err_msg:
                errors += 1
                # Выводим первую ошибку, остальные скрываем чтобы не спамить
                if errors == 1:
                    print(f"\n⚠️ Обнаружена битая запись (пропускаю): {err_msg}")
                    print(f"   Проблемный SQL (начало): {cmd[:100]}...")
                elif errors % 500 == 0:
                    print(f"⚠️ Пропущено ошибок: {errors}...")

        # Прогресс бар
        if i % 1000 == 0:
            sys.stdout.write(f"\r⏳ Обработано: {i}/{total} (Ошибок: {errors})")
            sys.stdout.flush()

    con.commit()
    
    # 5. Финальная проверка
    print("\n\n✅ Восстановление завершено.")
    try:
        cur.execute("SELECT count(*) FROM Posts;")
        posts = cur.fetchone()[0]
        print(f"📊 Постов в базе: {posts}")
        
        print("🔧 Перестраиваю поисковый индекс...")
        cur.execute("INSERT INTO PostsFTS(PostsFTS) VALUES('rebuild');")
        con.commit()
        print("✅ Индекс перестроен.")
        
    except Exception as e:
        print(f"⚠️ Не удалось проверить статистику: {e}")

    con.close()

if __name__ == "__main__":
    restore_db()