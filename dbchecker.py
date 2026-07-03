import sqlite3
import os
import sys
import json
import time
import re
from datetime import datetime

# Настройки цветов для терминала
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def get_db_path():
    """Пытается угадать имя базы данных."""
    candidates = ['dvach_bot.db', 'tgach.db', 'database.db']
    for db in candidates:
        if os.path.exists(db):
            return db
    return None

def format_size(size_bytes):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"


def quote_identifier(s):
    """Safely escapes SQLite identifiers."""
    escaped_s = s.replace('"', '""')
    return f'"{escaped_s}"'


def check_integrity(cur):
    print(f"\n{Colors.BOLD}1. Проверка физической целостности (integrity_check)...{Colors.ENDC}")
    start_time = time.time()
    try:
        cur.execute("PRAGMA integrity_check")
        result = cur.fetchone()[0]
        if result == "ok":
            print(f"{Colors.OKGREEN}✅ Целостность структуры базы данных: OK{Colors.ENDC}")
        else:
            print(f"{Colors.FAIL}⛔ ОБНАРУЖЕНЫ ПОВРЕЖДЕНИЯ: {result}{Colors.ENDC}")
    except Exception as e:
        print(f"{Colors.FAIL}Ошибка проверки целостности: {e}{Colors.ENDC}")
    print(f"   (Заняло {time.time() - start_time:.4f} сек)")

def get_table_statistics(cur, tables):
    print(f"\n{Colors.BOLD}2. Статистика таблиц{Colors.ENDC}")

    # Fetch valid table names from sqlite_master for whitelisting
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    valid_tables = {row[0] for row in cur.fetchall()}

    total_rows = 0
    print(f"{'Таблица':<25} | {'Строк':<10}")
    print("-" * 40)
    for table in tables:
        if table not in valid_tables:
            print(f"{table:<25} | {'NOT IN DB':<10}")
            continue
        if not re.match(r'^[a-zA-Z0-9_]+$', table):
            print(f"{table:<25} | {'INVALID NAME':<10}")
            continue
        try:
            safe_table = quote_identifier(table)
            cur.execute(f'SELECT COUNT(*) FROM {safe_table}')
            count = cur.fetchone()[0]
            print(f"{table:<25} | {count:<10}")
            total_rows += count
        except:
            print(f"{table:<25} | {'ERROR':<10}")
    print("-" * 40)
    print(f"{Colors.BOLD}Всего записей: {total_rows}{Colors.ENDC}")
    return total_rows

def find_logical_garbage(cur, tables):
    print(f"\n{Colors.BOLD}3. Поиск логического мусора (Orphans & Garbage){Colors.ENDC}")
    garbage_found = False

    # 3.1 Посты без доски
    cur.execute("""
        SELECT COUNT(*) FROM Posts 
        WHERE board_id NOT IN (SELECT board_id FROM Boards)
    """)
    orphaned_posts_board = cur.fetchone()[0]
    if orphaned_posts_board > 0:
        print(f"{Colors.FAIL}⚠️  Посты, ссылающиеся на несуществующие доски: {orphaned_posts_board}{Colors.ENDC}")
        garbage_found = True
    else:
        print(f"{Colors.OKGREEN}✓ Посты корректно привязаны к доскам{Colors.ENDC}")

    # 3.2 Мертвые треды (Запись в Threads есть, а ОП-поста в Posts нет)
    cur.execute("""
        SELECT COUNT(*) FROM Threads t
        LEFT JOIN Posts p ON t.thread_id = CAST(p.post_num AS TEXT)
        WHERE p.post_num IS NULL
    """)
    dead_threads = cur.fetchone()[0]
    if dead_threads > 0:
        print(f"{Colors.FAIL}⚠️  Треды без ОП-поста (битые записи в Threads): {dead_threads}{Colors.ENDC}")
        print(f"   {Colors.WARNING}-> Рекомендуется: DELETE FROM Threads WHERE thread_id NOT IN (SELECT CAST(post_num AS TEXT) FROM Posts){Colors.ENDC}")
        garbage_found = True
    else:
        print(f"{Colors.OKGREEN}✓ Все треды имеют живой ОП-пост{Colors.ENDC}")

    # 3.3 Посты-сироты (указан thread_id, но такого треда нет в таблице Threads)
    cur.execute("""
        SELECT COUNT(*) FROM Posts 
        WHERE thread_id IS NOT NULL 
        AND thread_id != CAST(post_num AS TEXT)
        AND thread_id NOT IN (SELECT thread_id FROM Threads)
    """)
    posts_orphaned_thread = cur.fetchone()[0]
    if posts_orphaned_thread > 0:
        print(f"{Colors.WARNING}⚠️  Посты, привязанные к удаленным тредам: {posts_orphaned_thread}{Colors.ENDC}")
        print(f"   (Это может быть нормально, если удаляли тред, но посты остались как 'призраки'. Лучше почистить)")
        garbage_found = True
    else:
        print(f"{Colors.OKGREEN}✓ Посты корректно привязаны к тредам{Colors.ENDC}")

    # 3.4 Мусор в очередях (ссылки на удаленные посты)
    tables_to_check = {
        "PostCopies": "post_num",
        "BroadcastQueue": "post_num",
        "NotificationQueue": "source_post_num",
        "Reports": "post_num"
    }
    
    # Fetch valid table names from sqlite_master for whitelisting
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    valid_tables = {row[0] for row in cur.fetchall()}

    orphan_tables = []
    for table, col in tables_to_check.items():
        if table in tables:
            if table not in valid_tables:
                print(f"{Colors.FAIL}⚠️  Пропущена таблица {table}: нет в базе{Colors.ENDC}")
                continue
            if not re.match(r'^[a-zA-Z0-9_]+$', table):
                print(f"{Colors.FAIL}⚠️  Пропущена таблица {table}: недопустимое имя{Colors.ENDC}")
                continue
            safe_table = quote_identifier(table)
            safe_col = quote_identifier(col)
            cur.execute(f"""
                SELECT COUNT(*) FROM {safe_table} t
                LEFT JOIN Posts p ON t.{safe_col} = p.post_num
                WHERE p.post_num IS NULL
            """)
            orphans = cur.fetchone()[0]
            if orphans > 0:
                print(f"{Colors.FAIL}⚠️  Мусор в таблице {table}: {orphans} записей (ссылаются на удаленные посты){Colors.ENDC}")
                garbage_found = True
                orphan_tables.append((table, col))
            else:
                print(f"{Colors.OKGREEN}✓ Таблица {table} чиста{Colors.ENDC}")

    # 3.5 Просроченные муты/баны (которые уже истекли, но висят в БД)
    current_ts = time.time()
    cur.execute("SELECT COUNT(*) FROM Mutes WHERE expires_at < ?", (current_ts,))
    expired_mutes = cur.fetchone()[0]
    if expired_mutes > 0:
        print(f"{Colors.WARNING}⚠️  Истекшие муты в базе (можно почистить): {expired_mutes}{Colors.ENDC}")
    else:
        print(f"{Colors.OKGREEN}✓ Актуальность таблицы Mutes в порядке{Colors.ENDC}")

    return garbage_found, dead_threads, posts_orphaned_thread, orphan_tables

def analyze_content(cur):
    print(f"\n{Colors.BOLD}4. Анализ контента (JSON и Медиа){Colors.ENDC}")
    print("Сканирование всех постов... (может занять время)")
    
    cur.execute("SELECT post_num, content FROM Posts")
    
    json_errors = 0
    total_files = 0
    empty_content = 0
    shadow_posts = 0
    
    counter = 0
    try:
        while True:
            rows = cur.fetchmany(1000)
            if not rows:
                break
            
            for row in rows:
                post_num = row['post_num']
                raw_content = row['content']
                counter += 1

                if not raw_content:
                    empty_content += 1
                    continue
                
                try:
                    data = json.loads(raw_content)
                    # Считаем файлы
                    if isinstance(data, dict):
                        files = data.get('files', [])
                        if files:
                            total_files += len(files)
                    else:
                        # Странно, если JSON не объект
                        pass
                except json.JSONDecodeError:
                    json_errors += 1

    except KeyboardInterrupt:
        print("\nПроцесс прерван пользователем.")
    
    # Также проверим кол-во теневых постов через SQL (быстрее)
    cur.execute("SELECT COUNT(*) FROM Posts WHERE is_shadow = 1")
    shadow_posts = cur.fetchone()[0]

    print(f"   - Просканировано постов: {counter}")
    if json_errors > 0:
        print(f"{Colors.FAIL}   - Постов с битым JSON: {json_errors}{Colors.ENDC}")
    else:
        print(f"{Colors.OKGREEN}   - Все JSON поля валидны{Colors.ENDC}")
    
    print(f"   - Всего медиа-файлов (ссылок): {total_files}")
    print(f"   - Пустых постов: {empty_content}")
    print(f"   - Теневых (Shadow) постов: {shadow_posts}")
    return json_errors > 0

def analyze_users(cur):
    print(f"\n{Colors.BOLD}5. Анализ пользователей{Colors.ENDC}")
    cur.execute("SELECT COUNT(*) FROM Users")
    total_users = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(DISTINCT user_id) FROM Users")
    unique_users = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM Users WHERE status = 'banned'")
    banned_users = cur.fetchone()[0]
    
    print(f"   - Записей в таблице Users: {total_users}")
    print(f"   - Уникальных User ID: {unique_users}")
    print(f"   - Активных банов (status='banned'): {banned_users}")

def print_recommendations(garbage_found, dead_threads, orphan_tables, posts_orphaned_thread, db_path):
    print(f"\n{Colors.HEADER}{Colors.BOLD}=== ИТОГОВЫЙ ОТЧЕТ ==={Colors.ENDC}")
    
    if garbage_found:
        print(f"{Colors.FAIL}⛔ В базе данных обнаружен мусор или несоответствия.{Colors.ENDC}")
        print("Рекомендуемые действия:")
        
        if dead_threads > 0:
            print(f"1. Выполнить очистку мертвых тредов:")
            print(f"   {Colors.OKCYAN}DELETE FROM Threads WHERE thread_id NOT IN (SELECT CAST(post_num AS TEXT) FROM Posts);{Colors.ENDC}")
            
        if orphan_tables:
            print("2. Очистить очереди от ссылок на несуществующие посты:")
            for tbl, col in orphan_tables:
                print(f"   {Colors.OKCYAN}DELETE FROM {tbl} WHERE {col} NOT IN (SELECT post_num FROM Posts);{Colors.ENDC}")

        if posts_orphaned_thread > 0:
            print("3. (Опционально) Удалить посты, чьи треды были удалены:")
            print(f"   {Colors.OKCYAN}DELETE FROM Posts WHERE thread_id IS NOT NULL AND thread_id != CAST(post_num AS TEXT) AND thread_id NOT IN (SELECT thread_id FROM Threads);{Colors.ENDC}")
            
    else:
        print(f"{Colors.OKGREEN}✅ Критических проблем в структуре данных не обнаружено.{Colors.ENDC}")

    # Проверка размера WAL файла
    wal_path = db_path + "-wal"
    if os.path.exists(wal_path):
        wal_size = os.path.getsize(wal_path)
        print(f"\nРазмер WAL-журнала: {format_size(wal_size)}")
        if wal_size > 50 * 1024 * 1024: # 50MB
            print(f"{Colors.WARNING}⚠️  WAL файл велик. Рекомендуется выполнить VACUUM или checkpoint.{Colors.ENDC}")

    print("\nДля полной оптимизации (сжатия) базы рекомендуется выполнить SQL команду:")
    print(f"{Colors.OKCYAN}VACUUM;{Colors.ENDC}")

def probe_database():
    db_path = get_db_path()

    if not db_path:
        print(f"{Colors.FAIL}❌ База данных не найдена в текущей директории.{Colors.ENDC}")
        print("Ожидались: dvach_bot.db или tgach.db")
        sys.exit(1)

    print(f"{Colors.HEADER}{Colors.BOLD}=== ЗАПУСК ГЛУБОКОГО АНАЛИЗА БД: {db_path} ==={Colors.ENDC}")
    print(f"Время запуска: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    file_size = os.path.getsize(db_path)
    print(f"Физический размер файла: {Colors.OKCYAN}{format_size(file_size)}{Colors.ENDC}")

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
    except Exception as e:
        print(f"{Colors.FAIL}Критическая ошибка подключения: {e}{Colors.ENDC}")
        sys.exit(1)

    check_integrity(cur)

    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cur.fetchall()]

    get_table_statistics(cur, tables)

    garbage_found, dead_threads, posts_orphaned_thread, orphan_tables = find_logical_garbage(cur, tables)

    if analyze_content(cur):
        garbage_found = True

    analyze_users(cur)

    print_recommendations(garbage_found, dead_threads, orphan_tables, posts_orphaned_thread, db_path)

    conn.close()

if __name__ == "__main__":
    probe_database()
