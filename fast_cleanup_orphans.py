import sqlite3

def clean_post_copies():
    conn = sqlite3.connect('dvach_bot.db')
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
        
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.execute("VACUUM")
    conn.close()
    print("Cleanup and vacuum done.")

if __name__ == '__main__':
    clean_post_copies()
