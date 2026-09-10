import sys
import os
import py_compile
import sqlite3
import ast
import json
import time

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

REPO_ROOT = r"c:\Users\danat\Desktop\dvachbot"
DB_PATH = os.path.join(REPO_ROOT, "dvach_bot.db")

PYTHON_FILES = [
    "ai_manager.py",
    "archive_manager.py",
    "banner_manager.py",
    "broadcaster.py",
    "combat_moderation_engine.py",
    "common/database.py",
    "common/html_utils.py",
    "common/spam_filter.py",
    "common/tts_engine.py",
    "common/work_engine.py",
    "delivery_manager.py",
    "drop_engine.py",
    "economy_extension.py",
    "handlers/message_router.py",
    "leaderboard_card.py",
    "lootbox_engine.py",
    "main.py",
    "post_helpers.py",
    "shared_state.py",
    "site_tgach/vision.py",
    "stats_generator.py",
    "summarize.py",
    "wardrobe_engine.py",
    "auction_engine.py",
    "whale_economy_engine.py",
    "scripts/sanitize_shadowbans_and_expired.py",
    "scripts/verify_m2_econ_adversarial.py",
    "scripts/verify_wal_safety.py",
]

def check_compilation():
    print("=== CHECK 1: PY_COMPILE ===")
    errors = []
    for rel_path in PYTHON_FILES:
        full_path = os.path.join(REPO_ROOT, rel_path)
        if not os.path.exists(full_path):
            print(f"⚠️ Missing file: {rel_path}")
            continue
        try:
            py_compile.compile(full_path, doraise=True)
            print(f"✅ COMPILED: {rel_path}")
        except py_compile.PyCompileError as e:
            print(f"❌ FAILED: {rel_path} -> {e}")
            errors.append((rel_path, str(e)))
    return errors

def check_sqlite_wal_and_integrity():
    print("\n=== CHECK 2: SQLITE WAL & INTEGRITY ===")
    if not os.path.exists(DB_PATH):
        print("❌ Database file does not exist!")
        return False
    
    db_size = os.path.getsize(DB_PATH)
    wal_size = os.path.getsize(DB_PATH + "-wal") if os.path.exists(DB_PATH + "-wal") else 0
    shm_size = os.path.getsize(DB_PATH + "-shm") if os.path.exists(DB_PATH + "-shm") else 0
    print(f"DB Size: {db_size:,} bytes ({db_size / (1024*1024):.2f} MB)")
    print(f"WAL Size: {wal_size:,} bytes ({wal_size / (1024*1024):.2f} MB)")
    print(f"SHM Size: {shm_size:,} bytes")

    # Connect strictly read-only
    uri = f"file:{DB_PATH}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    cur = conn.cursor()

    cur.execute("PRAGMA journal_mode")
    jmode = cur.fetchone()[0]
    print(f"Journal Mode: {jmode}")

    cur.execute("PRAGMA integrity_check")
    integrity = cur.fetchall()
    print(f"Integrity Check: {integrity}")

    cur.execute("PRAGMA quick_check")
    quick = cur.fetchall()
    print(f"Quick Check: {quick}")

    # Read-only test: verify write rejection
    try:
        cur.execute("CREATE TABLE _audit_test (x INT)")
        print("❌ FAILED: read-only connection allowed write!")
        return False
    except sqlite3.OperationalError as e:
        print(f"✅ READ-ONLY ENFORCED: {e}")

    conn.close()

    # Checkpoint check via separate connection if needed
    conn_chk = sqlite3.connect(DB_PATH)
    cur_chk = conn_chk.cursor()
    cur_chk.execute("PRAGMA wal_checkpoint(PASSIVE)")
    chk = cur_chk.fetchone()
    print(f"wal_checkpoint(PASSIVE): busy={chk[0]}, log_pages={chk[1]}, checkpointed={chk[2]}")
    conn_chk.close()
    return integrity == [('ok',)] and quick == [('ok',)]

def check_db_data_and_forensics():
    print("\n=== CHECK 3: DATABASE DATA & FORENSICS ===")
    uri = f"file:{DB_PATH}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    cur = conn.cursor()
    now_ts = int(time.time())

    # 1. Check expired mutes
    cur.execute("SELECT COUNT(*) FROM Mutes WHERE expires_at < ?", (now_ts,))
    expired_mutes = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM Mutes")
    total_mutes = cur.fetchone()[0]
    print(f"Mutes: total={total_mutes}, expired={expired_mutes}")

    # 2. Check hidden shadowbans in Users
    cur.execute("SELECT COUNT(*) FROM Users WHERE shadow_ban_media > 1 AND shadow_ban_media < ?", (now_ts,))
    exp_media = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM Users WHERE shadow_ban_sticker > 1 AND shadow_ban_sticker < ?", (now_ts,))
    exp_sticker = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM Users WHERE shadow_ban_gif > 1 AND shadow_ban_gif < ?", (now_ts,))
    exp_gif = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM Users WHERE cursed_until > 0 AND cursed_until < ?", (now_ts,))
    exp_cursed = cur.fetchone()[0]
    print(f"Expired TTL shadowbans in Users: media={exp_media}, sticker={exp_sticker}, gif={exp_gif}, cursed_until={exp_cursed}")

    # Active shadowbans
    cur.execute("SELECT COUNT(*) FROM Users WHERE shadow_ban_media = 1 OR shadow_ban_media > ?", (now_ts,))
    act_media = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM Users WHERE shadow_ban_sticker = 1 OR shadow_ban_sticker > ?", (now_ts,))
    act_sticker = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM Users WHERE shadow_ban_gif = 1 OR shadow_ban_gif > ?", (now_ts,))
    act_gif = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM Users WHERE cursed_until > ?", (now_ts,))
    act_cursed = cur.fetchone()[0]
    print(f"Active shadowbans in Users: media={act_media}, sticker={act_sticker}, gif={act_gif}, cursed_until={act_cursed}")

    # 3. User 8858659148 lootbox & stats audit
    print("\n--- User 8858659148 Audit ---")
    cur.execute("SELECT user_id, board_id, balance, posts_count, active_items FROM Users WHERE user_id = 8858659148")
    user_rows = cur.fetchall()
    print(f"Rows for 8858659148: {len(user_rows)}")
    for r in user_rows:
        print(f"  board={r[1]}, balance={r[2]}, posts={r[3]}, items={r[4][:100] if r[4] else None}")

    cur.execute("SELECT COUNT(*), SUM(amount) FROM UserTransactions WHERE user_id = 8858659148 AND category = 'lootbox'")
    lb_tx = cur.fetchone()
    print(f"  User 8858659148 lootbox transactions: count={lb_tx[0]}, sum={lb_tx[1]}")

    cur.execute("SELECT id, amount, category, description, timestamp FROM UserTransactions WHERE user_id = 8858659148 ORDER BY timestamp DESC LIMIT 5")
    recent_tx = cur.fetchall()
    print(f"  Recent transactions for 8858659148: {recent_tx}")

    # 4. Macroeconomy: 48h balance, Abu Yacht Fund, BankDeposits
    print("\n--- Macroeconomy 48h Audit ---")
    cur.execute("SELECT balance FROM Users WHERE user_id = 0 LIMIT 1")
    abu_fund_row = cur.fetchone()
    abu_fund = abu_fund_row[0] if abu_fund_row else 0
    print(f"Abu Yacht Fund (user_id=0): {abu_fund:,} ₪")

    cur.execute("SELECT COUNT(*), SUM(principal) FROM BankDeposits WHERE status = 'active'")
    dep_active = cur.fetchone()
    print(f"Active BankDeposits: count={dep_active[0]}, total_principal={dep_active[1]}")

    cur.execute("SELECT COUNT(*), SUM(amount) FROM UserTransactions WHERE timestamp >= 1788680200")
    tx_48h = cur.fetchone()
    print(f"48h UserTransactions (ts >= 1788680200): count={tx_48h[0]}, total_flow={tx_48h[1]}")

    cur.execute("SELECT category, COUNT(*), SUM(amount) FROM UserTransactions WHERE timestamp >= 1788680200 GROUP BY category")
    cats = cur.fetchall()
    print("48h Transactions by category:")
    for c in cats:
        print(f"  {c[0]}: count={c[1]}, net_amount={c[2]}")

    # 5. MusicRoasts table
    print("\n--- MusicRoasts Table Audit ---")
    try:
        cur.execute("SELECT COUNT(*) FROM MusicRoasts")
        mr_count = cur.fetchone()[0]
        cur.execute("SELECT id, user_id, artist, title, score, timestamp FROM MusicRoasts ORDER BY timestamp DESC LIMIT 3")
        mr_recent = cur.fetchall()
        print(f"MusicRoasts total rows: {mr_count}")
        print(f"Recent MusicRoasts: {mr_recent}")
    except Exception as e:
        print(f"MusicRoasts check: {e}")

    # 6. Orphan PostFiles
    cur.execute("SELECT COUNT(*) FROM PostFiles WHERE post_num NOT IN (SELECT post_num FROM Posts)")
    orphan_pf = cur.fetchone()[0]
    print(f"Orphan PostFiles: {orphan_pf}")

    conn.close()

def check_ast_integrity_and_facades():
    print("\n=== CHECK 4: AST INTEGRITY & FACADES ===")
    violations = []
    for rel_path in PYTHON_FILES:
        full_path = os.path.join(REPO_ROOT, rel_path)
        if not os.path.exists(full_path):
            continue
        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            code = f.read()

        try:
            tree = ast.parse(code, filename=rel_path)
        except SyntaxError as e:
            violations.append(f"SyntaxError in {rel_path}: {e}")
            continue

        for node in ast.walk(tree):
            # Check for dummy functions returning a constant without any logic
            if isinstance(node, ast.FunctionDef):
                # Ignore trivial property/overload/stub functions
                is_stub = any(isinstance(d, ast.Name) and d.id in ("overload", "abstractmethod") for d in node.decorator_list)
                if not is_stub and len(node.body) == 1:
                    stmt = node.body[0]
                    if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Constant):
                        if stmt.value.value in (True, False, "ok", "SUCCESS"):
                            # Check if name looks suspicious
                            if not node.name.startswith("is_") and not node.name.startswith("has_") and not node.name.startswith("should_"):
                                print(f"  Notice: single constant return in {rel_path}:{node.name}:{node.lineno} -> {stmt.value.value}")

    # Check compact_icon in post_helpers.py
    post_helpers_path = os.path.join(REPO_ROOT, "post_helpers.py")
    with open(post_helpers_path, "r", encoding="utf-8", errors="ignore") as f:
        ph_content = f.read()
    
    # Verify compact_icon is not added to custom_prefix
    if 'custom_prefix = badge_emoji + debuff_icons + prefix_str' in ph_content:
        print("✅ post_helpers.py: custom_prefix correctly omits compact_icon.")
    else:
        print("❌ post_helpers.py: custom_prefix does not match expected definition!")

    if 'author_prefix = ""  # wardrobe icons disabled in post headers' in ph_content:
        print("✅ post_helpers.py: format_thread_post_header author_prefix correctly disabled.")
    else:
        print("❌ post_helpers.py: format_thread_post_header author_prefix not disabled!")

if __name__ == "__main__":
    check_compilation()
    check_sqlite_wal_and_integrity()
    check_db_data_and_forensics()
    check_ast_integrity_and_facades()
