import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

with open(r"C:\Users\danat\Desktop\dvachbot\common\database.py", 'r', encoding='utf-8') as f:
    text = f.read()

print("Is 'db_sleep' in file?", 'db_sleep' in text)
print("Occurrences of 'db_sleep':", text.count('db_sleep'))

# Find line numbers for db_sleep definition or import
lines = text.splitlines()
for idx, line in enumerate(lines, 1):
    if 'db_sleep' in line:
        if 'import' in line or 'def ' in line or '=' in line and not 'await' in line:
            print(f"Line {idx} (def/import/assign): {line}")
