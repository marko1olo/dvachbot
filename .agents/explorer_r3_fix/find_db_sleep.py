import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

with open(r"C:\Users\danat\Desktop\dvachbot\common\database.py", 'r', encoding='utf-8') as f:
    lines = f.readlines()

print(f"Total lines in database.py: {len(lines)}")
for idx, line in enumerate(lines, 1):
    if 'db_sleep' in line:
        print(f"Line {idx}: {line.strip()}")
