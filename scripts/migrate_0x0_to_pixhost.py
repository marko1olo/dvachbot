"""
Migrate dead 0x0 queue tasks to pixhost tasks.
Since 0x0 is disabled (ZEROXZERO_ENABLED=0), we repurpose the 39k queue entries
to pixhost tasks, which will be processed by the backfill_pixhost.py script.

Run once: python scripts/migrate_0x0_to_pixhost.py
"""
import sys, os, sqlite3, time
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'dvach_bot.db')

print(f"Opening DB: {DB_PATH}")
conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA journal_mode=WAL;")
conn.execute("PRAGMA busy_timeout=60000;")
conn.execute("PRAGMA synchronous=NORMAL;")
db = conn
c = db.cursor()

# Show current state
c.execute("SELECT COUNT(*) FROM MirrorQueue WHERE mirror_type='0x0'")
cnt_0x0 = c.fetchone()[0]
print(f"Current 0x0 tasks in MirrorQueue: {cnt_0x0}")

c.execute("SELECT COUNT(*) FROM MirrorQueue WHERE mirror_type='pixhost'")
cnt_px = c.fetchone()[0]
print(f"Current pixhost tasks in MirrorQueue: {cnt_px}")

if cnt_0x0 == 0:
    print("No 0x0 tasks to migrate. Exiting.")
    db.close()
    sys.exit(0)

# Get 0x0 file_ids
c.execute("SELECT file_id FROM MirrorQueue WHERE mirror_type='0x0'")
file_ids_0x0 = [r[0] for r in c.fetchall()]
print(f"\nMigrating {len(file_ids_0x0)} tasks from 0x0 -> pixhost...")

# For each file_id in 0x0 queue:
# - Check if there's already a pixhost mirror (then just delete 0x0 task)
# - Check if there's already a pixhost queue entry (then just delete 0x0 task)
# - Otherwise, insert as pixhost task

migrated = 0
skipped_already_mirrored = 0
skipped_already_queued = 0
deleted_only = 0

BATCH = 500
for i in range(0, len(file_ids_0x0), BATCH):
    batch = file_ids_0x0[i:i+BATCH]
    
    for file_id in batch:
        # Check if already has pixhost mirror
        c.execute("SELECT 1 FROM FileMirrors WHERE file_id=? AND mirror_type='pixhost'", (file_id,))
        if c.fetchone():
            skipped_already_mirrored += 1
            # Delete the 0x0 task
            c.execute("DELETE FROM MirrorQueue WHERE file_id=? AND mirror_type='0x0'", (file_id,))
            continue
        
        # Check if already in pixhost queue
        c.execute("SELECT 1 FROM MirrorQueue WHERE file_id=? AND mirror_type='pixhost'", (file_id,))
        if c.fetchone():
            skipped_already_queued += 1
            # Delete the 0x0 task
            c.execute("DELETE FROM MirrorQueue WHERE file_id=? AND mirror_type='0x0'", (file_id,))
            continue
        
        # Check file type - pixhost only supports images, not video/audio
        c.execute("SELECT file_type FROM FileRegistry WHERE file_id=?", (file_id,))
        row = c.fetchone()
        if not row or row[0] not in ('image', 'photo'):
            # Not an image - just delete the 0x0 task, don't migrate
            c.execute("DELETE FROM MirrorQueue WHERE file_id=? AND mirror_type='0x0'", (file_id,))
            deleted_only += 1
            continue
        
        # Insert pixhost task and delete 0x0 task
        try:
            c.execute(
                "INSERT OR IGNORE INTO MirrorQueue (file_id, mirror_type, attempts, next_run_at) VALUES (?, 'pixhost', 0, ?)",
                (file_id, time.time())
            )
            c.execute("DELETE FROM MirrorQueue WHERE file_id=? AND mirror_type='0x0'", (file_id,))
            migrated += 1
        except Exception as e:
            print(f"Error for {file_id[:15]}: {e}")
    
    db.commit()
    done = min(i + BATCH, len(file_ids_0x0))
    print(f"  Progress: {done}/{len(file_ids_0x0)} processed...")

db.commit()
db.close()

print(f"\nDone!")
print(f"  Migrated to pixhost: {migrated}")
print(f"  Skipped (already mirrored): {skipped_already_mirrored}")
print(f"  Skipped (already queued): {skipped_already_queued}")
print(f"  Deleted (non-image): {deleted_only}")
