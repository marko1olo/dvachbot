import sys

sys.stdout.reconfigure(encoding='utf-8')

filepath = r"C:\Users\danat\Desktop\dvachbot\site_tgach\main.py"

with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

print("Search for _mark_random_dead_file definition:")
for idx, line in enumerate(lines, 1):
    if "_mark_random_dead_file" in line:
        print(f"Line {idx:5d}: {line.strip()}")

