import os

project_root = r"C:\Users\danat\Desktop\dvachbot"
output_file = r"C:\Users\danat\Desktop\dvachbot\.agents\explorer_r3\lock_analysis.txt"

db_lock_refs = []
db_sleep_refs = []
asyncio_sleep_refs = []

for root, dirs, files in os.walk(project_root):
    if ".agents" in root or "__pycache__" in root or ".git" in root or "venv" in root:
        continue
    for file in files:
        if file.endswith(".py"):
            path = os.path.join(root, file)
            rel_path = os.path.relpath(path, project_root)
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            for idx, line in enumerate(lines, 1):
                if "db_lock" in line:
                    db_lock_refs.append((rel_path, idx, line.strip()))
                if "db_sleep" in line:
                    db_sleep_refs.append((rel_path, idx, line.strip()))
                if "asyncio.sleep" in line and "common" in rel_path:
                    asyncio_sleep_refs.append((rel_path, idx, line.strip()))

with open(output_file, "w", encoding="utf-8") as out:
    out.write(f"=== DB_LOCK REFERENCES ({len(db_lock_refs)}) ===\n")
    for r in db_lock_refs:
        out.write(f"{r[0]}:{r[1]}: {r[2]}\n")
    
    out.write(f"\n=== DB_SLEEP REFERENCES ({len(db_sleep_refs)}) ===\n")
    for r in db_sleep_refs:
        out.write(f"{r[0]}:{r[1]}: {r[2]}\n")

    out.write(f"\n=== ASYNCIO.SLEEP IN COMMON ({len(asyncio_sleep_refs)}) ===\n")
    for r in asyncio_sleep_refs:
        out.write(f"{r[0]}:{r[1]}: {r[2]}\n")

print(f"Done! Written to {output_file}")
