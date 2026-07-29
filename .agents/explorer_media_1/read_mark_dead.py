import sys

sys.stdout.reconfigure(encoding='utf-8')

filepath = r"C:\Users\danat\Desktop\dvachbot\site_tgach\main.py"

with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

print("=== _mark_random_dead_file definition (Lines 505-535) ===")
for idx in range(504, min(535, len(lines))):
    print(f"{idx+1:5d}: {lines[idx]}")

