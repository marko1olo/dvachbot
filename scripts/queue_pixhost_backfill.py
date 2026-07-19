"""
Populate MirrorQueue with pixhost tasks for all image files missing pixhost mirror.
Run once on VPS: python scripts/queue_pixhost_backfill.py

Uses FileOwners as the primary source (175k entries) since FileRegistry only
covers ~39k files. File type is inferred from FileRegistry when available,
or from file_id prefix heuristic for orphan files.

Image prefix heuristics (from FileRegistry analysis):
  AgAC* -> image/photo (dominant, ~98% images)
  BQAC* -> may be image or document (include, let mirror_worker skip bad formats)

Run once, then mirror_worker.py processes them automatically.
"""
import sys, os, sqlite3, time
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'dvach_bot.db')
BATCH_SIZE = 1000

# Prefixes indicating image-type files (from FileRegistry analysis)
IMAGE_PREFIXES = ('AgAC', 'BQAC')


print(f"Opening DB: {DB_PATH}")
db = sqlite3.connect(DB_PATH)
db.execute("PRAGMA journal_mode=WAL")
c = db.cursor()

# Count candidates: files in FileOwners matching image prefixes
# that don't yet have a pixhost mirror AND aren't already in pixhost queue
prefix_cond = " OR ".join([f"fo.file_id LIKE '{p}%'" for p in IMAGE_PREFIXES])
count_query = f"""
    SELECT COUNT(DISTINCT fo.file_id)
    FROM FileOwners fo
    WHERE ({prefix_cond})
      AND NOT EXISTS (SELECT 1 FROM FileMirrors m WHERE m.file_id = fo.file_id AND m.mirror_type = 'pixhost')
      AND NOT EXISTS (SELECT 1 FROM MirrorQueue q WHERE q.file_id = fo.file_id AND q.mirror_type = 'pixhost')
"""
c.execute(count_query)
total_missing = c.fetchone()[0]
print(f"Image files (in FileOwners) missing pixhost mirror: {total_missing:,}")

if total_missing == 0:
    print("Nothing to do!")
    db.close()
    sys.exit(0)

print(f"\nEnqueueing {total_missing:,} pixhost tasks in batches of {BATCH_SIZE}...")

inserted = 0
skipped = 0
already_done = 0
now = time.time()

fetch_query = f"""
    SELECT DISTINCT fo.file_id
    FROM FileOwners fo
    WHERE ({prefix_cond})
      AND NOT EXISTS (SELECT 1 FROM FileMirrors m WHERE m.file_id = fo.file_id AND m.mirror_type = 'pixhost')
      AND NOT EXISTS (SELECT 1 FROM MirrorQueue q WHERE q.file_id = fo.file_id AND q.mirror_type = 'pixhost')
    LIMIT ?
"""

total_processed = 0
while True:
    c.execute(fetch_query, (BATCH_SIZE,))
    rows = c.fetchall()
    
    if not rows:
        break
    
    for (file_id,) in rows:
        try:
            c.execute(
                "INSERT OR IGNORE INTO MirrorQueue (file_id, mirror_type, attempts, next_run_at) VALUES (?, 'pixhost', 0, ?)",
                (file_id, now)
            )
            if c.rowcount > 0:
                inserted += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"  Error inserting {file_id[:15]}: {e}")
            skipped += 1
    
    db.commit()
    total_processed += len(rows)
    progress_pct = total_processed / total_missing * 100
    print(f"  [{progress_pct:.0f}%] Processed: {total_processed:,}/{total_missing:,} | Inserted: {inserted:,} | Skipped: {skipped:,}")

db.close()
print(f"\nDone!")
print(f"  Total inserted into MirrorQueue: {inserted:,}")
print(f"  Skipped (already in queue/mirrored): {skipped:,}")
print(f"mirror_worker.py will process these automatically at rate of ~20 files per 10s.")
estimated_hours = inserted / (20 / 10) / 3600
print(f"Estimated processing time: ~{estimated_hours:.1f} hours")
