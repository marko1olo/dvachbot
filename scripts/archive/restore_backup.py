import sqlite3
import os
import re
import sys


# === НАСТРОЙКИ ===
SQL_FILE = "backup.sql"
DB_FILE = "dvach_bot.db"
CLEAN_SQL_FILE = "backup_clean_temp.sql"
# =================


def remove_old_db(db_file):
    if os.path.exists(db_file):
        try:
            os.remove(db_file)
            print(f"🗑️ Старый файл {db_file} удален.")
        except PermissionError:
            print("❌ ОШИБКА: Закрой все программы, использующие базу!")
            return False
    return True


def read_and_clean_sql(sql_file):
    print(f"📖 Читаю и лечу файл {sql_file}...")
    try:
        with open(sql_file, 'r', encoding='utf-8-sig', errors='replace') as f:
            content = f.read()
    except Exception as e:
        print(f"❌ Ошибка чтения: {e}")
        return None

    pat_fts = (
        r'CREATE\s+VIRTUAL\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?'
        r'["`]?PostsFTS["`]?\s+USING\s+fts5\s*\(.*?\);'
    )
    content = re.sub(pat_fts, '', content, flags=re.IGNORECASE | re.DOTALL)

    content = content.replace('BEGIN TRANSACTION;', '').replace('COMMIT;', '')
    return content


def create_db_and_fts(db_file):
    con = sqlite3.connect(db_file)
    cur = con.cursor()

    cur.execute("PRAGMA journal_mode = WAL;")
    cur.execute("PRAGMA synchronous = OFF;")
    cur.execute("PRAGMA foreign_keys = OFF;")  # Важно!

    print("🔧 Создаю структуру FTS вручную...")
    cur.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS PostsFTS USING fts5(
            content,
            content='Posts',
            content_rowid='post_num'
        );
    """)
    return con, cur


def execute_sql_commands(con, cur, commands):
    total = len(commands)
    success = 0
    errors = 0

    cur.execute("BEGIN TRANSACTION;")

    for i, cmd in enumerate(commands):
        if not cmd.strip():
            continue

        try:
            cur.execute(cmd)
            success += 1
        except sqlite3.Error as e:
            err_msg = str(e)
            if "already exists" not in err_msg:
                errors += 1
                if errors == 1:
                    print(
                        f"\n⚠️ Обнаружена битая запись (пропускаю): {err_msg}"
                    )
                    print(f"   Проблемный SQL (начало): {cmd[:100]}...")
                elif errors % 500 == 0:
                    print(f"⚠️ Пропущено ошибок: {errors}...")

        if i % 1000 == 0:
            sys.stdout.write(
                f"\r⏳ Обработано: {i}/{total} (Ошибок: {errors})"
            )
            sys.stdout.flush()

    con.commit()


def verify_restore(con, cur):
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


def restore_db():
    print(f"🔧 Запуск восстановления БД '{DB_FILE}'...")

    if not os.path.exists(SQL_FILE):
        print(f"❌ Файл {SQL_FILE} не найден!")
        return

    if not remove_old_db(DB_FILE):
        return

    content = read_and_clean_sql(SQL_FILE)
    if content is None:
        return

    con, cur = create_db_and_fts(DB_FILE)

    print("🚀 Начинаю заливку данных (построчно)...")
    commands = content.split(';\n')

    execute_sql_commands(con, cur, commands)
    verify_restore(con, cur)

    con.close()


if __name__ == "__main__":
    restore_db()
