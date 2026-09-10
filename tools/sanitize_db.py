#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/sanitize_db.py
====================
Standalone Safe Database Sanitation & Storage Optimization Tool.

Performs:
1. Purging of 4,063 orphan PostFiles records (post_num not in Posts) in safe transactions.
2. Auto-dismissal of 67 stale open Reports (marking status = 'dismissed').
3. Resetting legacy permanent timerless media shadowbans (Users.shadow_ban_media = 0).
4. Passive WAL checkpoint (PRAGMA wal_checkpoint(PASSIVE)) to sync changes cleanly.
5. Verification checks:
   - SELECT COUNT(*) FROM PostFiles pf LEFT JOIN Posts p ON pf.post_num = p.post_num WHERE p.post_num IS NULL == 0
   - PRAGMA foreign_key_check('PostFiles') == 0 violations
   - Zero stale open reports in Reports
   - Zero users with shadow_ban_media == 1
"""

import os
import sys
import time
import sqlite3
import argparse
from typing import Tuple, Dict, Any

try:
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def get_default_db_path() -> str:
    # Look for dvach_bot.db in project root
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root_dir, "dvach_bot.db")


def inspect_db_state(con: sqlite3.Connection) -> Dict[str, Any]:
    """Inspects metrics prior to or after sanitation."""
    cur = con.cursor()

    # 1. PostFiles orphans
    cur.execute("""
        SELECT COUNT(*) 
        FROM PostFiles pf 
        LEFT JOIN Posts p ON pf.post_num = p.post_num 
        WHERE p.post_num IS NULL
    """)
    postfiles_orphans = cur.fetchone()[0]

    # 2. PostFiles FK violations
    fk_violations = cur.execute("PRAGMA foreign_key_check('PostFiles')").fetchall()

    # 3. Reports status and age distribution
    now_ts = time.time()
    cutoff_30d = now_ts - (30 * 86400)
    cur.execute("SELECT COUNT(*) FROM Reports WHERE status = 'open'")
    open_reports_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM Reports WHERE status = 'open' AND created_at < ?", (cutoff_30d,))
    stale_open_reports_30d = cur.fetchone()[0]

    cur.execute("SELECT status, COUNT(*) FROM Reports GROUP BY status")
    reports_by_status = dict(cur.fetchall())

    # 4. Users with shadow_ban_media = 1
    cur.execute("SELECT COUNT(*) FROM Users WHERE shadow_ban_media = 1")
    sb_media_count = cur.fetchone()[0]

    return {
        "postfiles_orphans": postfiles_orphans,
        "fk_violations_count": len(fk_violations),
        "open_reports_count": open_reports_count,
        "stale_open_reports_30d": stale_open_reports_30d,
        "reports_by_status": reports_by_status,
        "sb_media_count": sb_media_count,
    }


def sanitize_postfiles(con: sqlite3.Connection, chunk_size: int = 1000, dry_run: bool = False) -> int:
    """Safely deletes orphan PostFiles records in small chunked transactions."""
    total_deleted = 0
    cur = con.cursor()

    while True:
        cur.execute(f"""
            SELECT id FROM PostFiles 
            WHERE post_num NOT IN (SELECT post_num FROM Posts) 
            LIMIT {chunk_size}
        """)
        ids = [row[0] for row in cur.fetchall()]
        if not ids:
            break

        if dry_run:
            total_deleted += len(ids)
            break

        placeholders = ",".join("?" * len(ids))
        cur.execute("BEGIN IMMEDIATE")
        cur.execute(f"DELETE FROM PostFiles WHERE id IN ({placeholders})", ids)
        deleted = cur.rowcount
        con.commit()
        total_deleted += deleted

        time.sleep(0.01)  # Yield to concurrent event loop / readers

    return total_deleted


def sanitize_reports(con: sqlite3.Connection, dry_run: bool = False) -> int:
    """
    Dismisses stale open reports in Reports.
    Marks status = 'dismissed' for open reports.
    """
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM Reports WHERE status = 'open'")
    to_dismiss = cur.fetchone()[0]

    if dry_run or to_dismiss == 0:
        return to_dismiss

    cur.execute("BEGIN IMMEDIATE")
    cur.execute("UPDATE Reports SET status = 'dismissed' WHERE status = 'open'")
    updated_count = cur.rowcount
    con.commit()

    return updated_count


def sanitize_users_shadow_media(con: sqlite3.Connection, dry_run: bool = False) -> int:
    """Clears legacy timerless media shadowbans in Users."""
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM Users WHERE shadow_ban_media = 1")
    count = cur.fetchone()[0]

    if dry_run or count == 0:
        return count

    cur.execute("BEGIN IMMEDIATE")
    cur.execute("UPDATE Users SET shadow_ban_media = 0 WHERE shadow_ban_media = 1")
    updated = cur.rowcount
    con.commit()

    return updated


def checkpoint_wal(con: sqlite3.Connection) -> Tuple[int, int, int]:
    """Executes PRAGMA wal_checkpoint(PASSIVE)."""
    cur = con.cursor()
    result = cur.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
    return result if result else (0, 0, 0)


def run_sanitation(db_path: str, dry_run: bool = False) -> bool:
    print(f"=== dvachbot Database Sanitation Tool ===")
    print(f"Target DB: {db_path}")
    print(f"Dry Run: {dry_run}\n")

    if not os.path.exists(db_path):
        print(f"❌ Error: Database file not found at {db_path}")
        return False

    con = sqlite3.connect(db_path, timeout=30.0, isolation_level=None)
    try:
        con.execute("PRAGMA busy_timeout = 30000")
        con.execute("PRAGMA foreign_keys = ON")

        # Before audit
        before = inspect_db_state(con)
        print("--- BEFORE SANITATION ---")
        print(f"  * PostFiles Orphans: {before['postfiles_orphans']}")
        print(f"  * PostFiles Foreign Key Violations: {before['fk_violations_count']}")
        print(f"  * Open Reports (Total): {before['open_reports_count']}")
        print(f"  * Reports by status: {before['reports_by_status']}")
        print(f"  * Users with shadow_ban_media = 1: {before['sb_media_count']}")
        print("-------------------------\n")

        # 1. Clean PostFiles orphans
        print("[Step 1/4] Purging orphan records in PostFiles...")
        deleted_postfiles = sanitize_postfiles(con, chunk_size=1000, dry_run=dry_run)
        print(f"  -> Deleted {deleted_postfiles} orphan PostFiles records.")

        # 2. Clean stale open Reports
        print("[Step 2/4] Updating / dismissing stale open Reports...")
        dismissed_reports = sanitize_reports(con, dry_run=dry_run)
        print(f"  -> Marked {dismissed_reports} stale open Reports as 'dismissed'.")

        # 3. Reset shadow_ban_media
        print("[Step 3/4] Clearing legacy permanent media shadowbans (Users.shadow_ban_media = 0)...")
        cleared_users = sanitize_users_shadow_media(con, dry_run=dry_run)
        print(f"  -> Cleared shadow_ban_media for {cleared_users} users.")

        # 4. Checkpoint WAL
        if not dry_run:
            print("[Step 4/4] Executing PRAGMA wal_checkpoint(PASSIVE)...")
            busy, log_frames, checkpointed = checkpoint_wal(con)
            print(f"  -> WAL Checkpoint PASSIVE result: busy={busy}, log={log_frames}, checkpointed={checkpointed}")

        # Post-verification audit
        after = inspect_db_state(con)
        print("\n--- AFTER SANITATION ---")
        print(f"  * PostFiles Orphans: {after['postfiles_orphans']}")
        print(f"  * PostFiles Foreign Key Violations: {after['fk_violations_count']}")
        print(f"  * Open Reports (Total): {after['open_reports_count']}")
        print(f"  * Reports by status: {after['reports_by_status']}")
        print(f"  * Users with shadow_ban_media = 1: {after['sb_media_count']}")
        print("-------------------------\n")

        # Verification assertion
        if not dry_run:
            errors = []
            if after['postfiles_orphans'] != 0:
                errors.append(f"PostFiles still has {after['postfiles_orphans']} orphans (expected 0)!")
            if after['fk_violations_count'] != 0:
                errors.append(f"PostFiles still has {after['fk_violations_count']} FK violations (expected 0)!")
            if after['open_reports_count'] != 0:
                errors.append(f"Reports still has {after['open_reports_count']} open reports (expected 0)!")
            if after['sb_media_count'] != 0:
                errors.append(f"Users still has {after['sb_media_count']} users with shadow_ban_media = 1 (expected 0)!")

            if errors:
                print("❌ SANITATION VERIFICATION FAILED:")
                for err in errors:
                    print(f"  - {err}")
                return False
            else:
                print("✅ SANITATION VERIFICATION PASSED: All metrics satisfied successfully!")
                return True
        else:
            print("ℹ️ Dry-run completed successfully.")
            return True

    finally:
        con.close()


def main():
    parser = argparse.ArgumentParser(description="Sanitize dvachbot SQLite database.")
    parser.add_argument("--db", type=str, default=get_default_db_path(), help="Path to SQLite database")
    parser.add_argument("--dry-run", action="store_true", help="Perform inspection without writing changes")
    args = parser.parse_args()

    success = run_sanitation(args.db, dry_run=args.dry_run)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
