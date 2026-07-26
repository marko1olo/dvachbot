import sqlite3
import shutil
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

db_path = r'C:\Users\danat\Desktop\dvachbot\dvach_bot.db'
backup_path = r'C:\Users\danat\Desktop\dvachbot\dvach_bot_backup_before_postcopies_cleanup.db'

def main():
    print("======================================================================")
    print("🛡️ ШАГ 1: СОЗДАНИЕ ПОЛНОГО БЭКАПА БАЗЫ ДАННЫХ")
    print("======================================================================")
    
    if not os.path.exists(db_path):
        print(f"❌ База данных не найдена по пути {db_path}")
        return

    orig_size_mb = os.path.getsize(db_path) / (1024 * 1024)
    print(f"📦 Исходный размер {os.path.basename(db_path)}: {orig_size_mb:.2f} МБ")
    print(f"💾 Создание бэкапа в {os.path.basename(backup_path)}...")

    # Входим в SQLite с WAL checkpoint перед бэкапом
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        conn.close()
    except Exception as e:
        print(f"  ⚠️ Warning on WAL checkpoint: {e}")

    shutil.copy2(db_path, backup_path)
    backup_size_mb = os.path.getsize(backup_path) / (1024 * 1024)
    print(f"✅ Бэкап успешно создан! Размер бэкапа: {backup_size_mb:.2f} МБ")

    print("\n======================================================================")
    print("🔍 ШАГ 2: ПОДСЧЁТ УСТАРЕВШИХ ЗАПИСЕЙ POSTCOPIES (СТАРШЕ 14 ДНЕЙ)")
    print("======================================================================")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    days_14_ago = time.time() - (14 * 86400)

    # Находим пороговый post_num за 14 дней назад
    cur.execute("SELECT MIN(post_num) FROM Posts WHERE timestamp >= ?", (days_14_ago,))
    threshold_post_num = cur.fetchone()[0]

    if not threshold_post_num:
        cur.execute("SELECT MAX(post_num) - 50000 FROM Posts")
        threshold_post_num = cur.fetchone()[0] or 0

    print(f"  • Пороговый номер поста за 14 дней назад (timestamp >= {days_14_ago:.0f}): #{threshold_post_num}")

    cur.execute("SELECT COUNT(*) FROM PostCopies WHERE post_num < ?", (threshold_post_num,))
    to_delete_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM PostCopies WHERE post_num >= ?", (threshold_post_num,))
    to_keep_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM PostCopies")
    total_count = cur.fetchone()[0]

    print(f"  • Всего записей в PostCopies: {total_count:,}")
    print(f"  • Будет УДАЛЕНО (старше 14 дней, post_num < {threshold_post_num}): {to_delete_count:,}")
    print(f"  • Будет СОХРАНЕНО (последние 14 дней, post_num >= {threshold_post_num}): {to_keep_count:,}")

    conn.close()

if __name__ == '__main__':
    main()
