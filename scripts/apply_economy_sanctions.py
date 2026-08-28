# -*- coding: utf-8 -*-
"""
scripts/apply_economy_sanctions.py — Database Sanitization & Confiscation Script
1. Resets illicit balances of bot abusers (8802107011, 8669887559, 8858659148) to baseline 500 ₪.
2. Caps inflated invulnerability and protective timers (shield/tinfoil) to maximum 7 days.
3. Переводит изъятые шекели в Казну Абу (abu_yacht_fund).
4. Записывает транзакции конфискации в UserTransactions.
"""

import argparse
import datetime
import json
import os
import shutil
import sqlite3
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dvach_bot.db")
BOT_ABUSER_IDS = [8802107011, 8669887559, 8858659148]


def sanitize_active_items(items_raw: str, max_cap: int) -> tuple[str, bool]:
    """Capping inflated timers to max 7 days."""
    if not items_raw:
        return items_raw, False
    try:
        data = json.loads(items_raw)
    except Exception:
        return items_raw, False

    modified = False
    for k in ("shield_until", "reflect_shield_until", "tinfoil_until", "tinfoil_hat", "janitor_until"):
        if k in data and isinstance(data[k], (int, float)) and data[k] > max_cap:
            data[k] = max_cap
            modified = True

    return json.dumps(data, ensure_ascii=False), modified


def apply_sanctions(db_path: str, dry_run: bool = False) -> dict:
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found at {db_path}")

    now = int(time.time())
    max_cap = now + 7 * 86400

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    results = {
        "timestamp": datetime.datetime.now().isoformat(),
        "dry_run": dry_run,
        "affected_bots": [],
        "total_confiscated": 0.0,
        "fund_before": 0.0,
        "fund_after": 0.0,
    }

    try:
        # Fetch Abu Fund before
        cursor.execute("SELECT value FROM GlobalStats WHERE key = 'abu_yacht_fund'")
        fund_row = cursor.fetchone()
        fund_before = float(fund_row['value']) if fund_row and fund_row['value'] else 0.0
        results["fund_before"] = fund_before

        total_confiscated = 0.0

        for uid in BOT_ABUSER_IDS:
            cursor.execute("SELECT user_id, board_id, balance, active_items FROM Users WHERE user_id = ?", (uid,))
            user_rows = cursor.fetchall()
            if not user_rows:
                continue

            bot_info = {
                "user_id": uid,
                "boards": [],
                "old_total_balance": 0.0,
                "new_total_balance": 500.0,
                "confiscated": 0.0,
                "items_sanitized": False,
            }

            tot_bal = sum(float(r['balance'] or 0.0) for r in user_rows)
            bot_info["old_total_balance"] = tot_bal

            confiscated_from_user = max(0.0, tot_bal - 500.0)
            bot_info["confiscated"] = confiscated_from_user
            total_confiscated += confiscated_from_user

            for r in user_rows:
                b_id = r['board_id']
                raw_items = r['active_items'] or "{}"
                sanitized_items, was_mod = sanitize_active_items(raw_items, max_cap)
                if was_mod:
                    bot_info["items_sanitized"] = True

                # Set balance on primary board 'b' to 500.0, and 0 on other boards
                new_b_bal = 500.0 if b_id == 'b' else 0.0

                bot_info["boards"].append({
                    "board_id": b_id,
                    "old_balance": float(r['balance'] or 0.0),
                    "new_balance": new_b_bal,
                })

                if not dry_run:
                    cursor.execute(
                        "UPDATE Users SET balance = ?, active_items = ? WHERE user_id = ? AND board_id = ?",
                        (new_b_bal, sanitized_items, uid, b_id)
                    )

            if not dry_run and confiscated_from_user > 0:
                cursor.execute(
                    """
                    INSERT INTO UserTransactions (user_id, amount, category, description, timestamp)
                    VALUES (?, ?, 'confiscation', ?, ?)
                    """,
                    (
                        uid,
                        -confiscated_from_user,
                        f"Конфискация средств, накрученных через эксплойт лутбоксов ({confiscated_from_user:,.0f} ₪ в Казну Абу)",
                        now
                    )
                )

            results["affected_bots"].append(bot_info)

        results["total_confiscated"] = total_confiscated
        results["fund_after"] = fund_before + total_confiscated

        if not dry_run and total_confiscated > 0:
            cursor.execute(
                "INSERT INTO GlobalStats (key, value) VALUES ('abu_yacht_fund', ?) ON CONFLICT(key) DO UPDATE SET value = ?",
                (str(results["fund_after"]), str(results["fund_after"]))
            )
            conn.commit()

        return results

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Apply economy sanctions and sanitize abuser accounts.")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="Path to SQLite database")
    parser.add_argument("--apply", action="store_true", help="Apply changes (default is dry-run)")
    args = parser.parse_args()

    dry_run = not args.apply
    mode_str = "DRY-RUN (NO CHANGES)" if dry_run else "APPLYING SANCTIONS TO LIVE DATABASE"

    print("=" * 80)
    print(f"ECONOMY SANCTIONS ENGINE: {mode_str}")
    print(f"Target Database: {args.db}")
    print("=" * 80)

    if not dry_run:
        # Create a backup before modifying
        backup_path = f"{args.db}.backup_pre_sanctions_{int(time.time())}"
        print(f"📦 Creating backup at: {backup_path}")
        shutil.copy2(args.db, backup_path)

    res = apply_sanctions(args.db, dry_run=dry_run)

    print(f"\nAbu Yacht Fund Before: {res['fund_before']:,.2f} ₪")
    print(f"Total Confiscated:     {res['total_confiscated']:,.2f} ₪")
    print(f"Abu Yacht Fund After:  {res['fund_after']:,.2f} ₪")

    print("\n--- AFFECTED ACCOUNTS ---")
    for b in res["affected_bots"]:
        print(f"User ID: {b['user_id']}")
        print(f"  Old Balance: {b['old_total_balance']:,.2f} ₪ -> New Balance: {b['new_total_balance']:,.2f} ₪")
        print(f"  Confiscated: {b['confiscated']:,.2f} ₪")
        print(f"  Items Timers Sanitized: {b['items_sanitized']}")

    if dry_run:
        print("\n💡 This was a dry run. To execute changes, run with: python scripts/apply_economy_sanctions.py --apply")
    else:
        print("\n✅ Sanctions successfully committed to database!")


if __name__ == "__main__":
    main()
