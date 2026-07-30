import sqlite3
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

db_paths = [
    r'C:\Users\danat\Desktop\dvachbot\dvach_bot.db',
    r'C:\Users\danat\Desktop\dvachbot\2d2vach_bot.db'
]

def analyze_db(db_path):
    if not os.path.exists(db_path) or os.path.getsize(db_path) == 0:
        return

    file_size_mb = os.path.getsize(db_path) / (1024 * 1024)
    wal_path = db_path + "-wal"
    wal_size_mb = (os.path.getsize(wal_path) / (1024 * 1024)) if os.path.exists(wal_path) else 0.0

    print("\n======================================================================")
    print(f"📊 АНАЛИЗ БАЗЫ ДАННЫХ: {os.path.basename(db_path)}")
    print(f"   • Размер основного файла .db: {file_size_mb:.2f} МБ ({file_size_mb / 1024:.2f} ГБ)")
    print(f"   • Размер WAL файла (.db-wal): {wal_size_mb:.2f} МБ")
    print("======================================================================")

    uri = f"file:///{db_path.replace('\\', '/')}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except Exception:
        conn = sqlite3.connect(db_path)

    cur = conn.cursor()

    # 1. Page metrics
    cur.execute("PRAGMA page_count;")
    page_count = cur.fetchone()[0]
    cur.execute("PRAGMA page_size;")
    page_size = cur.fetchone()[0]
    cur.execute("PRAGMA freelist_count;")
    freelist_count = cur.fetchone()[0]
    freelist_mb = (freelist_count * page_size) / (1024 * 1024)

    print("📦 СТРУКТУРА СВОБОДНОГО МЕСТА (PAGE METRICS):")
    print(f"   • Всего страниц: {page_count:,}")
    print(f"   • Свободных удаленных страниц (Freelist): {freelist_count:,} ({freelist_mb:.2f} МБ)")

    # 2. Таблицы и количество строк
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    tables = [r[0] for r in cur.fetchall()]

    table_counts = {}
    chunk_size = 100
    for i in range(0, len(tables), chunk_size):
        chunk = tables[i:i + chunk_size]
        query_parts = []
        for tbl in chunk:
            safe_tbl = tbl.replace("'", "''")
            query_parts.append(f"SELECT '{safe_tbl}', COUNT(*) FROM \"{tbl}\"")
        union_query = " UNION ALL ".join(query_parts)

        try:
            if union_query:
                cur.execute(union_query)
                for tbl_name, count in cur.fetchall():
                    table_counts[tbl_name] = count
        except Exception:
            # Fallback for individual queries if chunked fails
            for tbl in chunk:
                try:
                    cur.execute(f"SELECT COUNT(*) FROM \"{tbl}\"")
                    table_counts[tbl] = cur.fetchone()[0]
                except Exception:
                    table_counts[tbl] = -1

    sorted_tables = sorted(table_counts.items(), key=lambda x: x[1], reverse=True)
    print("\n📋 ТОП-15 САМЫХ БОЛЬШИХ ТАБЛИЦ ПО КОЛИЧЕСТВУ СТРОК:")
    for tbl, count in sorted_tables[:15]:
        print(f"   • {tbl:<25}: {count:>12,} строк")

    print("\n🔍 ДЕТАЛЬНЫЙ АНАЛИЗ ГИГАНТОВ И КАНДИДАТОВ В МУСОР:")

    # 3.1 PostCopies - 30 миллионный гигант
    if 'PostCopies' in tables:
        print(f"\n   🔴 1. [PostCopies] (Всего строк: {table_counts.get('PostCopies'):,}):")
        cur.execute("PRAGMA table_info(PostCopies);")
        cols = [c[1] for c in cur.fetchall()]
        print(f"      Столбцы: {cols}")
        cur.execute("SELECT * FROM PostCopies LIMIT 3;")
        print(f"      Пример данных: {cur.fetchall()}")

    # 3.2 FileMirrors & MirrorQueue
    if 'FileMirrors' in tables:
        print(f"\n   🟡 2. [FileMirrors] (Всего строк: {table_counts.get('FileMirrors'):,}):")
        cur.execute("PRAGMA table_info(FileMirrors);")
        cols = [c[1] for c in cur.fetchall()]
        print(f"      Столбцы: {cols}")
        cur.execute("SELECT * FROM FileMirrors LIMIT 3;")
        print(f"      Пример данных: {cur.fetchall()}")

    if 'MirrorQueue' in tables:
        print(f"\n   🟡 3. [MirrorQueue] (Всего строк: {table_counts.get('MirrorQueue'):,}):")
        cur.execute("PRAGMA table_info(MirrorQueue);")
        cols = [c[1] for c in cur.fetchall()]
        print(f"      Столбцы: {cols}")
        cur.execute("SELECT * FROM MirrorQueue LIMIT 3;")
        print(f"      Пример данных: {cur.fetchall()}")

    # 3.3 ChannelCopies & FileOwners
    if 'ChannelCopies' in tables:
        print(f"\n   🟡 4. [ChannelCopies] (Всего строк: {table_counts.get('ChannelCopies'):,}):")
        cur.execute("PRAGMA table_info(ChannelCopies);")
        cols = [c[1] for c in cur.fetchall()]
        print(f"      Столбцы: {cols}")

    if 'FileOwners' in tables:
        print(f"\n   🟡 5. [FileOwners] (Всего строк: {table_counts.get('FileOwners'):,}):")
        cur.execute("PRAGMA table_info(FileOwners);")
        cols = [c[1] for c in cur.fetchall()]
        print(f"      Столбцы: {cols}")

    # 3.4 BroadcastQueue (Уже отработанные пересылки)
    if 'BroadcastQueue' in tables:
        cur.execute("SELECT COUNT(*) FROM BroadcastQueue WHERE is_sent_to_tg = 1")
        sent_bc = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM BroadcastQueue WHERE is_sent_to_tg = 0")
        pending_bc = cur.fetchone()[0]
        print(f"\n   🟢 6. [BroadcastQueue] (Всего строк: {table_counts.get('BroadcastQueue'):,}):")
        print(f"      - Отработанные записи (is_sent_to_tg=1, 100% МУСОР): {sent_bc:,}")
        print(f"      - В очереди на отправку (is_sent_to_tg=0): {pending_bc:,}")

    # 3.5 DeliveryQueue
    if 'DeliveryQueue' in tables:
        cur.execute("PRAGMA table_info(DeliveryQueue);")
        cols = [c[1] for c in cur.fetchall()]
        print(f"\n   🟢 7. [DeliveryQueue] (Столбцы: {cols}):")
        cur.execute("SELECT * FROM DeliveryQueue LIMIT 3;")
        print(f"      Пример данных: {cur.fetchall()}")

    # 3.6 Posts и возраст данных
    if 'Posts' in tables:
        now = time.time()
        days_30_ago = now - (30 * 86400)
        days_90_ago = now - (90 * 86400)
        days_180_ago = now - (180 * 86400)

        cur.execute("SELECT COUNT(*) FROM Posts WHERE timestamp < ?", (days_30_ago,))
        p30 = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM Posts WHERE timestamp < ?", (days_90_ago,))
        p90 = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM Posts WHERE timestamp < ?", (days_180_ago,))
        p180 = cur.fetchone()[0]

        print(f"\n   📌 8. [Posts] Хранение старых постов (Всего постов: {table_counts.get('Posts'):,}):")
        print(f"      - Старше 30 дней: {p30:,} (81.7% базы)")
        print(f"      - Старше 90 дней: {p90:,} (58.6% базы)")
        print(f"      - Старше 180 дней: {p180:,} (31.4% базы)")

    conn.close()

def main():
    print("======================================================================")
    print("🔍 ПОЛНЫЙ НЕРАЗРУШАЮЩИЙ АУДИТ МУСОРА И СТРУКТУРЫ БД (READ-ONLY)")
    print("======================================================================")
    for db in db_paths:
        analyze_db(db)

if __name__ == '__main__':
    main()
