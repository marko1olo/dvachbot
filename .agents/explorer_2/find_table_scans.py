import sqlite3
import re
import os

db_path = r'C:\Users\danat\Desktop\dvachbot\dvach_bot.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Extract queries from common/database.py, delivery_manager.py, broadcaster.py, main.py
files_to_scan = [
    r'C:\Users\danat\Desktop\dvachbot\common\database.py',
    r'C:\Users\danat\Desktop\dvachbot\delivery_manager.py',
    r'C:\Users\danat\Desktop\dvachbot\broadcaster.py',
    r'C:\Users\danat\Desktop\dvachbot\main.py',
]

queries = []
for filepath in files_to_scan:
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    # find sql blocks
    matches = re.findall(r'(?:SELECT|UPDATE|DELETE)\s+[^"\';]+\s+FROM\s+[^"\';]+', content, re.IGNORECASE)
    for m in matches:
        q = ' '.join(m.split())
        # clean python formatting like f-strings
        if '{' in q or '}' in q or '%' in q:
            continue
        queries.append((os.path.basename(filepath), q))

print(f"Total query strings collected: {len(queries)}")

scan_reports = []
for fname, q in queries:
    # try running explain query plan
    # replace ? with mock value or 1
    q_param_count = q.count('?')
    params = [1] * q_param_count
    try:
        cursor.execute(f"EXPLAIN QUERY PLAN {q}", params)
        rows = cursor.fetchall()
        for r in rows:
            plan_detail = str(r[3])
            if 'SCAN TABLE' in plan_detail or 'SCAN' in plan_detail:
                scan_reports.append((fname, q, plan_detail))
    except Exception as e:
        pass

print(f"\n--- TABLE SCANS FOUND ({len(scan_reports)}) ---")
seen = set()
for fname, q, plan in scan_reports:
    key = (fname, plan, q[:60])
    if key not in seen:
        seen.add(key)
        print(f"\nFile: {fname}\nPlan: {plan}\nQuery: {q[:120]}")

conn.close()
