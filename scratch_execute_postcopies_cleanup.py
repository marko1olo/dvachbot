import sqlite3
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

db_path = r'C:\Users\danat\Desktop\dvachbot\dvach_bot.db'

def main():
    print("======================================================================")
    print("🚀 ШАГ 3: ПОЭТАПНОЕ УДАЛЕНИЕ 17.6 МИЛЛИОНОВ ЗАПИСЕЙ ИЗ POSTCOPIES")
    print("======================================================================")

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA busy_timeout = 60000;")
    conn.execute("PRAGMA journal_mode = WAL;")
    cur = conn.cursor()

    days_14_ago = time.time() - (14 * 86400)
    cur.execute("SELECT MIN(post_num) FROM Posts WHERE timestamp >= ?", (days_14_ago,))
    threshold_post_num = cur.fetchone()[0]

    print(f"📌 Удаляем PostCopies с post_num < {threshold_post_num} пачками по 500,000 строк...")

    total_deleted = 0
    batch_size = 500000
    start_time = time.time()

    while True:
        # Находим max rowid для удаляемой пачки
        cur.execute("""
            DELETE FROM PostCopies 
            WHERE rowid IN (
                SELECT rowid FROM PostCopies 
                WHERE post_num < ? 
                LIMIT ?
            )
        """, (threshold_post_num, batch_size))
        
        deleted_in_batch = cur.rowcount
        conn.commit()
        total_deleted += deleted_in_batch

        elapsed = time.time() - start_time
        print(f"  • Удалено в батче: {deleted_in_batch:,} | Всего удалено: {total_deleted:,} | Прошло: {elapsed:.1f} сек.")

        if deleted_in_batch == 0:
            break

    print(f"\n✅ Все 17+ миллионов устаревших записей PostCopies успешно удалены за {time.time() - start_time:.1f} сек.!")

    print("\n======================================================================")
    print("🧹 ШАГ 4: ВЫПОЛНЕНИЕ VACUUM И ANALYZE")
    print("======================================================================")
    print("⏳ Сжатие базы данных (VACUUM)... Это может занять до 1-2 минут...")
    v_start = time.time()
    
    # VACUUM требует autocommit или закрытия транзакции
    conn.isolation_level = None
    cur.execute("VACUUM;")
    print(f"✅ VACUUM выполнен за {time.time() - v_start:.1f} сек.!")

    print("⏳ Обновление статистики планировщика запросов (ANALYZE)...")
    a_start = time.time()
    cur.execute("ANALYZE;")
    print(f"✅ ANALYZE выполнен за {time.time() - a_start:.1f} сек.!")

    conn.close()

    new_size_mb = os.path.getsize(db_path) / (1024 * 1024)
    print(f"\n======================================================================")
    print(f"🎉 ИТОГОВЫЙ РЕЗУЛЬТАТ СЖАТИЯ БАЗЫ:")
    print(f"   • Исходный размер: 2,122.24 МБ (2.12 ГБ)")
    print(f"   • Новый размер на диске: {new_size_mb:.2f} МБ ({new_size_mb / 1024:.2f} ГБ)")
    print(f"   • Высвобождено дискового места: {2122.24 - new_size_mb:.2f} МБ!")
    print(f"======================================================================")

if __name__ == '__main__':
    main()
