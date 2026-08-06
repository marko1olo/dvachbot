"""
Mirror coverage dashboard - shows current state of all mirror types.
Run: python scripts/mirror_coverage.py
"""
import sys, sqlite3, time
sys.stdout.reconfigure(encoding='utf-8')

db = sqlite3.connect('dvach_bot.db', timeout=30.0)
db.execute("PRAGMA journal_mode=WAL;")
db.execute("PRAGMA busy_timeout=30000;")
c = db.cursor()

print("=" * 60)
print("MIRROR COVERAGE DASHBOARD")
print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 60)

# Total files by type
c.execute("""
    SELECT file_type, COUNT(*) as cnt
    FROM FileRegistry
    GROUP BY file_type
    ORDER BY cnt DESC
""")
print("\n[FileRegistry] Files by type:")
total_reg = 0
for row in c.fetchall():
    print(f"  {row[0] or 'NULL'}: {row[1]:,}")
    total_reg += row[1]
print(f"  TOTAL: {total_reg:,}")

# Total files in FileOwners
c.execute("SELECT COUNT(*) FROM FileOwners")
total_owners = c.fetchone()[0]
print(f"\n[FileOwners] Total tracked files: {total_owners:,}")

# Mirror coverage by type
c.execute("""
    SELECT mirror_type, COUNT(*) as cnt
    FROM FileMirrors
    GROUP BY mirror_type
    ORDER BY cnt DESC
""")
print("\n[FileMirrors] Mirrors created:")
mirrors = {}
for row in c.fetchall():
    mirrors[row[0]] = row[1]
    print(f"  {row[0]}: {row[1]:,}")

# Coverage rates (vs FileOwners total)
print("\n[Coverage] vs FileOwners ({:,} total):".format(total_owners))
for mtype, cnt in mirrors.items():
    pct = cnt / total_owners * 100 if total_owners > 0 else 0
    print(f"  {mtype}: {cnt:,} / {total_owners:,} = {pct:.1f}%")

# Queue status
c.execute("""
    SELECT mirror_type, COUNT(*) as cnt, 
           SUM(CASE WHEN attempts > 0 THEN 1 ELSE 0 END) as attempted,
           MAX(attempts) as max_attempts
    FROM MirrorQueue
    GROUP BY mirror_type
    ORDER BY cnt DESC
""")
print("\n[MirrorQueue] Pending work:")
for row in c.fetchall():
    print(f"  {row[0]}: {row[1]:,} pending | {row[2] or 0:,} attempted | max_attempts={row[3]}")

# Images specifically (catbox vs pixhost coverage)
c.execute("""
    SELECT 
        COUNT(DISTINCT fo.file_id) as total_images,
        COUNT(DISTINCT cat.file_id) as has_catbox,
        COUNT(DISTINCT px.file_id) as has_pixhost
    FROM FileOwners fo
    LEFT JOIN FileMirrors cat ON cat.file_id = fo.file_id AND cat.mirror_type = 'catbox'
    LEFT JOIN FileMirrors px ON px.file_id = fo.file_id AND px.mirror_type = 'pixhost'
    WHERE (fo.file_id LIKE 'AgAC%' OR fo.file_id LIKE 'BQAC%')
""")
row = c.fetchone()
total_imgs = row[0]
has_catbox = row[1]
has_pixhost = row[2]
print(f"\n[Images specifically] (AgAC+BQAC prefix, ~{total_imgs:,} files):")
print(f"  Has catbox:  {has_catbox:,} / {total_imgs:,} = {has_catbox/total_imgs*100:.1f}%")
print(f"  Has pixhost: {has_pixhost:,} / {total_imgs:,} = {has_pixhost/total_imgs*100:.1f}%")
both = 0
c.execute("""
    SELECT COUNT(DISTINCT fo.file_id)
    FROM FileOwners fo
    WHERE (fo.file_id LIKE 'AgAC%' OR fo.file_id LIKE 'BQAC%')
      AND EXISTS (SELECT 1 FROM FileMirrors m WHERE m.file_id = fo.file_id AND m.mirror_type = 'catbox')
      AND EXISTS (SELECT 1 FROM FileMirrors m WHERE m.file_id = fo.file_id AND m.mirror_type = 'pixhost')
""")
both = c.fetchone()[0]
print(f"  Has both:    {both:,} / {total_imgs:,} = {both/total_imgs*100:.1f}%")
neither_catbox_no_pixhost = total_imgs - max(has_catbox, has_pixhost)
print(f"  No mirrors:  ~{total_imgs - has_catbox - has_pixhost + both:,}")

db.close()
print("\n" + "=" * 60)
