import sqlite3

def clean_post_copies():
    conn = sqlite3.connect('dvach_bot.db')
    try: conn.execute('PRAGMA journal_mode=WAL')
    except: pass
    try: conn.execute('PRAGMA synchronous=NORMAL')
    except: pass
    try: conn.execute('PRAGMA busy_timeout=15000')
    except: pass
    try: conn.execute('PRAGMA wal_autocheckpoint=1000')
    except: pass
    cursor = conn.cursor()
    
    print("Checking for orphans in PostCopies...")
    cursor.execute("SELECT COUNT(*) FROM PostCopies WHERE NOT EXISTS (SELECT 1 FROM Posts WHERE Posts.post_num = PostCopies.post_num)")
    orphans = cursor.fetchone()[0]
    print(f"Orphaned PostCopies: {orphans}")
    
    if orphans > 0:
        print("Cleaning up orphans in PostCopies (Fast Delete)...")
        conn.execute("BEGIN IMMEDIATE")
        cursor.execute("DELETE FROM PostCopies WHERE NOT EXISTS (SELECT 1 FROM Posts WHERE Posts.post_num = PostCopies.post_num)")
        deleted = cursor.rowcount
        conn.execute("COMMIT")
        print(f"Deleted {deleted} orphans.")
        
    print("Checking for orphans in ChannelCopies...")
    cursor.execute("SELECT COUNT(*) FROM ChannelCopies WHERE NOT EXISTS (SELECT 1 FROM Posts WHERE Posts.post_num = ChannelCopies.post_num)")
    c_orphans = cursor.fetchone()[0]
    print(f"Orphaned ChannelCopies: {c_orphans}")

    if c_orphans > 0:
        print("Cleaning up orphans in ChannelCopies (Fast Delete)...")
        conn.execute("BEGIN IMMEDIATE")
        cursor.execute("DELETE FROM ChannelCopies WHERE NOT EXISTS (SELECT 1 FROM Posts WHERE Posts.post_num = ChannelCopies.post_num)")
        deleted = cursor.rowcount
        conn.execute("COMMIT")
        print(f"Deleted {deleted} orphans.")
        
    try:
        conn.execute("DROP TABLE IF EXISTS _stress_table")
        print("Dropped _stress_table if present.")
    except Exception as e:
        print(f"Non-fatal error dropping _stress_table: {e}")

    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except Exception as e:
        print(f"WAL checkpoint non-fatal error: {e}")

    try:
        conn.execute("VACUUM")
        print("VACUUM completed successfully.")
    except sqlite3.OperationalError as e:
        print(f"VACUUM skipped due to lock contention: {e}")
        try:
            conn.execute("PRAGMA optimize")
            print("PRAGMA optimize executed as fallback.")
        except Exception:
            pass

    conn.close()
    print("Cleanup done.")

if __name__ == '__main__':
    clean_post_copies()
