import contextlib
# Файл: maintenance.py
import os
import sqlite3
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from common.config import DB_NAME



def _resolve_post_num_threshold(cur, cutoff_ts: float) -> int | None:
    cur.execute("SELECT MIN(post_num) FROM Posts WHERE timestamp >= ?", (cutoff_ts,))
    row = cur.fetchone()
    if row and isinstance(row[0], (int, float)):
        return int(row[0])
    cur.execute("SELECT MAX(post_num) FROM Posts WHERE timestamp < ?", (cutoff_ts,))
    row = cur.fetchone()
    if row and isinstance(row[0], (int, float)):
        return int(row[0]) + 1
    return None


def _sync_chunked_delete(con, table: str, where_sql: str, params: tuple, batch_size: int = 2000) -> int:
    cur = con.cursor()
    total_deleted = 0
    bsize = max(100, int(batch_size))
    query = f"DELETE FROM {table} WHERE rowid IN (SELECT rowid FROM {table} WHERE {where_sql} LIMIT ?)"
    while True:
        cur.execute(query, (*params, bsize))
        deleted = cur.rowcount or 0
        con.commit()
        total_deleted += deleted
        if deleted < bsize:
            break
        time.sleep(0.01)
    return total_deleted


def clean_old_postcopies(con, retention_days: int = 3, batch_size: int = 2000) -> int:
    """
    Удаляет устаревшие связки доставки PostCopies перед VACUUM небольшими порциями,
    чтобы освобожденные страницы были возвращены операционной системе и не создавалась монопольная блокировка.
    """
    try:
        cutoff_ts = time.time() - (retention_days * 86400)
        cur = con.cursor()
        thresh = _resolve_post_num_threshold(cur, cutoff_ts)
        if thresh is not None:
            total_deleted = _sync_chunked_delete(con, "PostCopies", "post_num < ?", (thresh,), batch_size=batch_size)
            print(f"🗑️ Удалены устаревшие связки PostCopies ({total_deleted:,} строк, до поста #{thresh}).")
            return total_deleted
    except Exception as ex:
        print(f"⚠️ Пропуск очистки PostCopies: {ex}")
    return 0


def clean_old_channelcopies(con, retention_days: int = 7, batch_size: int = 2000) -> int:
    try:
        cutoff_ts = time.time() - (retention_days * 86400)
        cur = con.cursor()
        thresh = _resolve_post_num_threshold(cur, cutoff_ts)
        if thresh is not None:
            total_deleted = _sync_chunked_delete(con, "ChannelCopies", "post_num < ?", (thresh,), batch_size=batch_size)
            print(f"🗑️ Удалены устаревшие ChannelCopies ({total_deleted:,} строк, до поста #{thresh}).")
            return total_deleted
    except Exception as ex:
        print(f"⚠️ Пропуск очистки ChannelCopies: {ex}")
    return 0


def clean_stale_mirror_queue(con, retention_days: int = 7, max_attempts: int = 10, batch_size: int = 2000) -> int:
    total_deleted = 0
    try:
        cutoff_ts = time.time() - (retention_days * 86400)
        total_deleted += _sync_chunked_delete(
            con,
            "MirrorQueue",
            "EXISTS (SELECT 1 FROM FileMirrors fm WHERE fm.file_id = MirrorQueue.file_id AND fm.mirror_type = MirrorQueue.mirror_type)",
            (),
            batch_size=batch_size,
        )
        total_deleted += _sync_chunked_delete(con, "MirrorQueue", "next_run_at < ?", (cutoff_ts,), batch_size=batch_size)
        total_deleted += _sync_chunked_delete(con, "MirrorQueue", "attempts >= ?", (max_attempts,), batch_size=batch_size)
        print(f"🗑️ Удалены устаревшие задачи MirrorQueue ({total_deleted:,} строк).")
    except Exception as ex:
        print(f"⚠️ Пропуск очистки MirrorQueue: {ex}")
    return total_deleted


def clean_old_moneydrop_messages(con, retention_hours: int = 24, batch_size: int = 2000) -> int:
    total_deleted = 0
    try:
        cutoff_ts = time.time() - (retention_hours * 3600)
        cur = con.cursor()
        bsize = max(100, int(batch_size))
        query = """
            DELETE FROM MoneyDropMessages
            WHERE rowid IN (
                SELECT mdm.rowid
                FROM MoneyDropMessages mdm
                LEFT JOIN MoneyDrops md ON mdm.drop_id = md.drop_id
                WHERE md.drop_id IS NULL
                   OR (md.status != 'active' AND COALESCE(md.claimed_at, md.refunded_at, md.created_at, 0) < ?)
                LIMIT ?
            )
        """
        while True:
            cur.execute(query, (cutoff_ts, bsize))
            deleted = cur.rowcount or 0
            con.commit()
            total_deleted += deleted
            if deleted < bsize:
                break
            time.sleep(0.01)
        print(f"🗑️ Удалены устаревшие MoneyDropMessages ({total_deleted:,} строк).")
    except Exception as ex:
        print(f"⚠️ Пропуск очистки MoneyDropMessages: {ex}")
    return total_deleted


def clean_old_media_reposts(con, retention_days: int = 180, batch_size: int = 2000) -> int:
    try:
        cutoff_ts = time.time() - (retention_days * 86400)
        total_deleted = _sync_chunked_delete(
            con,
            "MediaReposts",
            "times = 1 AND first_seen IS NOT NULL AND first_seen < ?",
            (cutoff_ts,),
            batch_size=batch_size,
        )
        print(f"🗑️ Удалены устаревшие MediaReposts ({total_deleted:,} строк).")
        return total_deleted
    except Exception as ex:
        print(f"⚠️ Пропуск очистки MediaReposts: {ex}")
    return 0


def run_maintenance():
    """
    Выполняет VACUUM и ANALYZE для базы данных.
    ВАЖНО: Запускать только при остановленных боте и сайте!
    """
    if not os.path.exists(DB_NAME):
        print(f"Ошибка: Файл базы данных не найден по пути: {DB_NAME}")
        return False

    # Защита от запуска при работающем боте (проверка bot.lock)
    lock_path = os.path.join(os.path.dirname(os.path.abspath(DB_NAME)), "bot.lock")
    if os.path.exists(lock_path):
        try:
            with open(lock_path, "r", encoding="utf-8") as lf:
                live_pid = int(lf.read().strip())
            import psutil
            if psutil.pid_exists(live_pid):
                print(f"⛔ ОШИБКА: Бот всё ещё работает (PID={live_pid}). Запуск обслуживания отменён во избежание дедлока БД.")
                return False
        except Exception:
            pass

    print(f"Подключение к базе данных: {DB_NAME}")
    try:
        with contextlib.closing(sqlite3.connect(DB_NAME, timeout=15.0)) as con:
            try: con.execute('PRAGMA journal_mode=WAL')
            except Exception: pass
            try: con.execute('PRAGMA synchronous=NORMAL')
            except Exception: pass
            try: con.execute('PRAGMA busy_timeout=120000')
            except Exception: pass
            try: con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            except Exception: pass

            clean_old_postcopies(con, retention_days=3)
            clean_old_channelcopies(con, retention_days=7)
            clean_stale_mirror_queue(con, retention_days=7)
            clean_old_moneydrop_messages(con, retention_hours=24)
            clean_old_media_reposts(con, retention_days=180)

            print("⏳ Запуск VACUUM для сжатия файла базы данных...")
            con.execute("VACUUM;")
            print("✅ VACUUM успешно завершен.")

            print("⏳ Запуск ANALYZE для оптимизации будущих запросов...")
            con.execute("ANALYZE;")
            print("✅ ANALYZE успешно завершен.")

            try: con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            except Exception: pass

        print("\nОбслуживание базы данных успешно завершено!")

    except Exception as e:
        print(f"⛔ КРИТИЧЕСКАЯ ОШИБКА во время обслуживания: {e}")

if __name__ == "__main__":
    print("--- Скрипт обслуживания базы данных ---")
    print("!!! ВНИМАНИЕ: Перед запуском убедитесь, что и бот, и сайт ПОЛНОСТЬЮ ОСТАНОВЛЕНЫ. !!!")

    if "-y" in sys.argv or "--yes" in sys.argv:
        run_maintenance()
    else:
        answer = input("Продолжить? (y/n): ").lower()
        if answer == 'y':
            run_maintenance()
        else:
            print("Операция отменена.")
