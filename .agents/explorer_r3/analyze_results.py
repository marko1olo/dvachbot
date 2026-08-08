from collections import defaultdict

db_lock_by_file = defaultdict(int)
db_sleep_by_file = defaultdict(int)
asyncio_sleep_by_file = defaultdict(int)

with open(r"C:\Users\danat\Desktop\dvachbot\.agents\explorer_r3\lock_analysis.txt", "r", encoding="utf-8") as f:
    current_section = None
    for line in f:
        line = line.strip()
        if "=== DB_LOCK REFERENCES" in line:
            current_section = "db_lock"
            continue
        elif "=== DB_SLEEP REFERENCES" in line:
            current_section = "db_sleep"
            continue
        elif "=== ASYNCIO.SLEEP IN COMMON" in line:
            current_section = "asyncio_sleep"
            continue

        if not line or ":" not in line:
            continue

        file_path = line.split(":")[0]
        if current_section == "db_lock":
            db_lock_by_file[file_path] += 1
        elif current_section == "db_sleep":
            db_sleep_by_file[file_path] += 1
        elif current_section == "asyncio_sleep":
            asyncio_sleep_by_file[file_path] += 1

print("--- DB_LOCK BY FILE ---")
for k, v in sorted(db_lock_by_file.items(), key=lambda x: x[1], reverse=True):
    print(f"{k}: {v}")

print("\n--- DB_SLEEP BY FILE ---")
for k, v in sorted(db_sleep_by_file.items(), key=lambda x: x[1], reverse=True):
    print(f"{k}: {v}")

print("\n--- ASYNCIO_SLEEP IN COMMON BY FILE ---")
for k, v in sorted(asyncio_sleep_by_file.items(), key=lambda x: x[1], reverse=True):
    print(f"{k}: {v}")
