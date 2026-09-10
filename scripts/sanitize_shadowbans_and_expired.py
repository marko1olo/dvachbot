# -*- coding: utf-8 -*-
"""
scripts/sanitize_shadowbans_and_expired.py
==========================================
Database Sanitation & Shadowban TTL Migration Script for DvachBot.

Addresses findings from Explorer R3 audit:
1. Cleans expired cursed_until timestamps in Users.
2. Cleans expired debuffs (shit_until, vomit_until, schizo_pill_until, cursed_until, peppersprayed_until)
   from Users.active_items JSON.
3. Removes permanent shadow_ban_sticker and shadow_ban_gif flags from Users without TTL
   (restoring innocent and low-post users).
4. Prunes expired TTL-based shadowbans (where flag > 1 is an expiration timestamp).
5. Synchronizes Users.posts_count with Posts table to eliminate the legacy 0-post bug.
"""

import sys
import os
import time
import json
import sqlite3
import argparse
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "dvach_bot.db"


def sanitize_database(db_path: Path, dry_run: bool = False):
    if not db_path.exists():
        print(f"❌ Database not found at: {db_path}")
        sys.exit(1)

    print(f"🔧 Connecting to SQLite database: {db_path} (dry_run={dry_run})")
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    now_ts = int(time.time())
    print(f"⏰ Current Unix Timestamp: {now_ts}")

    # =========================================================================
    # 1. Clean expired cursed_until in Users
    # =========================================================================
    cur.execute("SELECT COUNT(*) FROM Users WHERE cursed_until > 0 AND cursed_until < ?", (now_ts,))
    expired_curses_count = cur.fetchone()[0]

    cur.execute("SELECT user_id, board_id, cursed_until FROM Users WHERE cursed_until > 0 AND cursed_until < ?", (now_ts,))
    expired_curses = cur.fetchall()
    for uid, bid, c_until in expired_curses:
        print(f"  [CURSE] User {uid} on board /{bid}/: expired cursed_until={c_until} ({now_ts - c_until}s ago)")

    if not dry_run and expired_curses_count > 0:
        cur.execute("UPDATE Users SET cursed_until = 0 WHERE cursed_until > 0 AND cursed_until < ?", (now_ts,))
        print(f"  ✅ Reset {cur.rowcount} expired cursed_until entries to 0.")
    else:
        print(f"  ℹ️ Found {expired_curses_count} expired cursed_until entries.")

    # =========================================================================
    # 2. Clean expired active_items JSON debuffs
    # =========================================================================
    cur.execute("SELECT user_id, board_id, active_items FROM Users WHERE active_items IS NOT NULL AND active_items != ''")
    rows = cur.fetchall()
    cleaned_active_items_count = 0
    debuff_keys = ["shit_until", "vomit_until", "schizo_pill_until", "cursed_until", "peppersprayed_until"]
    cleaned_details = {k: 0 for k in debuff_keys}

    for uid, bid, raw_items in rows:
        try:
            items = json.loads(raw_items)
            if not isinstance(items, dict):
                continue
            modified = False
            for k in debuff_keys:
                if k in items:
                    val = items[k]
                    if isinstance(val, (int, float)) and val > 0 and val < now_ts:
                        del items[k]
                        modified = True
                        cleaned_details[k] += 1

            if modified:
                cleaned_active_items_count += 1
                if not dry_run:
                    cur.execute(
                        "UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                        (json.dumps(items), uid, bid)
                    )
        except Exception as e:
            print(f"  ⚠️ Error parsing active_items for user {uid} on /{bid}/: {e}")

    print(f"  ✅ Processed {len(rows)} Users; cleaned expired debuffs for {cleaned_active_items_count} records.")
    for k, cnt in cleaned_details.items():
        if cnt > 0:
            print(f"     - {k}: {cnt} expired keys removed")

    # =========================================================================
    # 3. Remove permanent shadow_ban_sticker and shadow_ban_gif flags
    # =========================================================================
    cur.execute("SELECT user_id, board_id, posts_count FROM Users WHERE shadow_ban_sticker = 1")
    stuck_stickers = cur.fetchall()
    print(f"  ℹ️ Found {len(stuck_stickers)} users with permanent shadow_ban_sticker=1.")
    for uid, bid, posts in stuck_stickers:
        print(f"     - User {uid} (board /{bid}/, {posts} posts)")

    cur.execute("SELECT user_id, board_id, posts_count FROM Users WHERE shadow_ban_gif = 1")
    stuck_gifs = cur.fetchall()
    print(f"  ℹ️ Found {len(stuck_gifs)} users with permanent shadow_ban_gif=1.")
    for uid, bid, posts in stuck_gifs:
        print(f"     - User {uid} (board /{bid}/, {posts} posts)")

    if not dry_run:
        cur.execute("UPDATE Users SET shadow_ban_sticker = 0 WHERE shadow_ban_sticker = 1")
        print(f"  ✅ Lifted permanent sticker shadowbans for {cur.rowcount} users.")
        cur.execute("UPDATE Users SET shadow_ban_gif = 0 WHERE shadow_ban_gif = 1")
        print(f"  ✅ Lifted permanent gif shadowbans for {cur.rowcount} users.")

    # =========================================================================
    # 4. Prune expired TTL-based shadowbans (> 1 treated as timestamp)
    # =========================================================================
    if not dry_run:
        cur.execute("UPDATE Users SET shadow_ban_sticker = 0 WHERE shadow_ban_sticker > 1 AND shadow_ban_sticker < ?", (now_ts,))
        ttl_sticker = cur.rowcount
        cur.execute("UPDATE Users SET shadow_ban_gif = 0 WHERE shadow_ban_gif > 1 AND shadow_ban_gif < ?", (now_ts,))
        ttl_gif = cur.rowcount
        cur.execute("UPDATE Users SET shadow_ban_media = 0 WHERE shadow_ban_media > 1 AND shadow_ban_media < ?", (now_ts,))
        ttl_media = cur.rowcount
        print(f"  ✅ Pruned expired TTL shadowbans: sticker={ttl_sticker}, gif={ttl_gif}, media={ttl_media}")

    # =========================================================================
    # 5. Synchronize Users.posts_count with real counts from Posts table
    # =========================================================================
    print("  🔄 Synchronizing Users.posts_count with real counts from Posts...")
    if not dry_run:
        cur.execute("""
            UPDATE Users
            SET posts_count = (
                SELECT COUNT(*) FROM Posts
                WHERE Posts.author_id = Users.user_id AND Posts.board_id = Users.board_id
            )
            WHERE Users.user_id > 0
        """)
        print(f"  ✅ Updated posts_count for {cur.rowcount} user records.")

    if not dry_run:
        conn.commit()
        print("💾 All changes successfully committed to database.")
    else:
        conn.rollback()
        print("🔍 Dry run completed — no changes were committed.")

    conn.close()
    print("🎉 Sanitation completed successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sanitize DvachBot shadowbans and expired debuffs.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to SQLite database file")
    parser.add_argument("--dry-run", action="store_true", help="Run without committing changes")
    args = parser.parse_args()

    sanitize_database(args.db, dry_run=args.dry_run)
