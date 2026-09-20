# -*- coding: utf-8 -*-
"""
scripts/safe_online_cleanup.py
Безопасная фоновая очистка устаревших связок доставки (PostCopies) на ЖИВОЙ базе.
Работает параллельно с запущенным ботом и сайтом:
- Удаляет чанками по 2000 строк
- Делает микро-паузы 0.05с для предотвращения lock contention
- Выполняет пассивные wal_checkpoint
- НЕ ТРОГАЕТ пользователей (таблица Users полностью неприкосновенна)
"""

import argparse
import os
import sqlite3
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dvach_bot.db"))



def run_safe_online_cleanup(retention_days: int = 3, batch_size: int = 2000, limit: int = 0, dry_run: bool = False):
    if not os.path.exists(DB_PATH):
        print(f"❌ База данных не найдена: {DB_PATH}")
        return

    print(f"🔍 Подключение к БД: {DB_PATH}")
    if dry_run:
        print("⚠️ РЕЖИМ DRY-RUN: никакие данные удаляться не будут!")

    # Высокий busy_timeout позволяет мирно ждать, если живой бот выполняет запись
    conn = sqlite3.connect(DB_PATH, timeout=60.0)
    cur = conn.cursor()

    cur.execute("PRAGMA busy_timeout = 60000;")
    cur.execute("PRAGMA synchronous = NORMAL;")

    # 1. Проверяем целостность таблицы пользователей (гарантия юзерских данных)
    cur.execute("SELECT count(*) FROM Users;")
    users_count = cur.fetchone()[0]
    print(f"👥 Таблица Users проверена: {users_count:,} анонов (НЕ ТРОГАЕМ).")

    # 2. Находим порог давности retention_days
    cutoff_ts = time.time() - (retention_days * 86400)
    cur.execute("SELECT MIN(post_num) FROM Posts WHERE timestamp >= ?", (cutoff_ts,))
    row = cur.fetchone()
    threshold_post_num = row[0] if row and row[0] else None

    if not threshold_post_num:
        print("ℹ️ Не удалось определить пороговый пост. База пуста или все посты слишком старые.")
        conn.close()
        return

    # 3. Считаем, сколько связок PostCopies подлежит удалению
    cur.execute("SELECT count(*) FROM PostCopies WHERE post_num < ?", (threshold_post_num,))
    total_to_delete = cur.fetchone()[0]

    cur.execute("SELECT count(*) FROM PostCopies;")
    total_postcopies = cur.fetchone()[0]

    print(f"📊 Всего связок в PostCopies: {total_postcopies:,}")
    print(f"🗑️ Связок старше {retention_days} дней к удалению (до поста #{threshold_post_num}): {total_to_delete:,}")

    if dry_run:
        print("✅ Проверка завершена (DRY-RUN). Удаление не производилось.")
        conn.close()
        return

    if total_to_delete == 0:
        print("✅ Устаревших записей в PostCopies нет. Очистка не требуется.")
        conn.close()
        return

    target_to_delete = min(total_to_delete, limit) if limit > 0 else total_to_delete
    if limit > 0:
        print(f"🎯 Установлен лимит на удаление: {target_to_delete:,} строк")

    # 4. Батчевое удаление с микро-паузами (чтобы живой бот не ловил database is locked)
    deleted_total = 0
    start_time = time.time()
    batch_num = 0

    while deleted_total < target_to_delete:
        current_batch = min(batch_size, target_to_delete - deleted_total)
        try:
            cur.execute("""
                DELETE FROM PostCopies
                WHERE rowid IN (
                    SELECT rowid FROM PostCopies
                    WHERE post_num < ?
                    LIMIT ?
                )
            """, (threshold_post_num, current_batch))
            deleted = cur.rowcount
            conn.commit()

            if deleted <= 0:
                break

            deleted_total += deleted
            batch_num += 1

            if batch_num % 5 == 0 or deleted_total >= target_to_delete:
                pct = min(100.0, (deleted_total / target_to_delete) * 100) if target_to_delete > 0 else 100.0
                elapsed = time.time() - start_time
                speed = deleted_total / elapsed if elapsed > 0 else 0
                print(f"  ⏳ Удалено: {deleted_total:,} / {target_to_delete:,} ({pct:.1f}%) | Скорость: {speed:,.0f} строк/сек...")

            # Периодический пассивный checkpoint журнала
            if batch_num % 15 == 0:
                try:
                    cur.execute("PRAGMA wal_checkpoint(PASSIVE);")
                except Exception:
                    pass

            # Микро-пауза, отдаем диск живому боту
            time.sleep(0.04)

        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower():
                # Если бот сейчас пишет — вежливо ждем 0.5с
                time.sleep(0.5)
                continue
            raise

    # Финальный checkpoint
    try:
        cur.execute("PRAGMA wal_checkpoint(PASSIVE);")
    except Exception:
        pass

    elapsed_total = time.time() - start_time
    cur.execute("SELECT count(*) FROM PostCopies;")
    rem_postcopies = cur.fetchone()[0]

    # Финальная проверка Users
    cur.execute("SELECT count(*) FROM Users;")
    final_users_count = cur.fetchone()[0]

    print("\n" + "="*50)
    print("✅ БЕЗОПАСНАЯ ОНЛАЙН-ОЧИСТКА ЗАВЕРШЕНА!")
    print(f"⏱️ Затрачено времени: {elapsed_total:.1f} сек")
    print(f"🗑️ Удалено просроченных связок: {deleted_total:,}")
    print(f"📦 Осталось активных связок PostCopies: {rem_postcopies:,}")
    print(f"👥 Таблица Users: {final_users_count:,} (100% нетронута)")
    print("="*50)

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Безопасная онлайн-очистка PostCopies на живой БД")
    parser.add_argument("--days", type=int, default=3, help="Срок хранения связок в днях (по умолчанию: 3)")
    parser.add_argument("--batch-size", type=int, default=2000, help="Размер батча за одну транзакцию (по умолчанию: 2000)")
    parser.add_argument("--limit", type=int, default=0, help="Максимальное количество строк для удаления (0 = без ограничений)")
    parser.add_argument("--dry-run", action="store_true", help="Только показать объем данных без реального удаления")

    args = parser.parse_args()
    run_safe_online_cleanup(
        retention_days=args.days,
        batch_size=args.batch_size,
        limit=args.limit,
        dry_run=args.dry_run
    )

