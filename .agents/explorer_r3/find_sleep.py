import re
import sys

with open(r"C:\Users\danat\Desktop\dvachbot\common\database.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

print(f"Total lines in database.py: {len(lines)}")

db_sleep_matches = []
asyncio_sleep_matches = []
other_sleep_matches = []
imports = []

for idx, line in enumerate(lines, 1):
    if "import" in line and ("db_sleep" in line or "sleep" in line):
        imports.append((idx, line.strip()))
    if "db_sleep" in line:
        db_sleep_matches.append((idx, line.strip()))
    if "asyncio.sleep" in line:
        asyncio_sleep_matches.append((idx, line.strip()))
    elif "sleep(" in line and "db_sleep" not in line:
        other_sleep_matches.append((idx, line.strip()))

print("\n--- IMPORTS ---")
for idx, line in imports:
    print(f"Line {idx}: {line}")

print("\n--- DB_SLEEP USAGES ---")
for idx, line in db_sleep_matches:
    print(f"Line {idx}: {line}")

print("\n--- ASYNCIO.SLEEP USAGES ---")
for idx, line in asyncio_sleep_matches:
    print(f"Line {idx}: {line}")

print("\n--- OTHER SLEEP USAGES ---")
for idx, line in other_sleep_matches:
    print(f"Line {idx}: {line}")
