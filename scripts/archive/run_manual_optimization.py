import sqlite3
import time

DB_PATH = "dvach_bot.db"

print("🔧 Запуск ручной оптимизации базы данных...")
con = sqlite3.connect(DB_PATH)
con.execute("PRAGMA journal_mode=WAL;")

# 1. Очистка PostCopies старше 7 дней
POST_COPY_RETENTION_SECONDS = 7 * 24 * 3600
POST_COPY_RETENTION_LIMIT = 5000

copy_cutoff = time.time() - POST_COPY_RETENTION_SECONDS
row = con.execute(
    "SELECT post_num FROM Posts ORDER BY post_num DESC LIMIT 1 OFFSET ?",
    (POST_COPY_RETENTION_LIMIT,)
).fetchone()
copy_floor_post_num = row[0] if row else 0

print(f"Ограничение копий: post_num < {copy_floor_post_num}, timestamp < {copy_cutoff}")

# Удаление старых копий пачками по 50 000 строк
total_deleted_copies = 0
while True:
    cur = con.execute("""
        DELETE FROM PostCopies WHERE rowid IN (
            SELECT rowid FROM PostCopies 
            WHERE post_num < ? AND post_num IN (
                SELECT post_num FROM Posts WHERE timestamp < ?
            )
            LIMIT 50000
        )
    """, (copy_floor_post_num, copy_cutoff))
    count = cur.rowcount
    con.commit()
    total_deleted_copies += count
    print(f"Удалено {count} записей из PostCopies (всего удалено: {total_deleted_copies})...")
    if count < 50000:
        break

# 2. Архивация старых тредов (старше 14 дней), которые не архивировались из-за бага
cutoff_thread = time.time() - 14 * 24 * 3600
cur = con.execute("UPDATE Threads SET is_archived = 1 WHERE last_updated_at < ? AND is_archived = 0", (cutoff_thread,))
print(f"Переведено в архив тредов: {cur.rowcount}")
con.commit()

# 3. УДАЛЕНИЕ ОТМЕНЕНО ПО ТРЕБОВАНИЮ: Сайт использует эти архивные треды.
# архивные треды и их посты больше не удаляются.

# 4. Очистка сирот (Orphans)
cleanup_targets = [
    ("PostCopies", "post_num"), ("ChannelCopies", "post_num"),
    ("BroadcastQueue", "post_num"), ("Reports", "post_num")
]
for table, col in cleanup_targets:
    cur = con.execute(f"DELETE FROM {table} WHERE {col} NOT IN (SELECT post_num FROM Posts)")
    print(f"Удалено {cur.rowcount} орфанных строк из {table}.")
    con.commit()

# 5. Очистка просроченных мутов
cur = con.execute("DELETE FROM Mutes WHERE expires_at < ?", (time.time(),))
print(f"Удалено просроченных мутов: {cur.rowcount}")
con.commit()

# 6. Запуск сжатия базы (VACUUM)
print("Запуск VACUUM (перестройка и сжатие файла базы, это займет немного времени)...")
start_v = time.time()
con.execute("VACUUM;")
print(f"VACUUM успешно завершен за {time.time() - start_v:.2f} сек!")

con.close()
print("✅ Оптимизация завершена успешно!")
