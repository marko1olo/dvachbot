import sys

sys.stdout.reconfigure(encoding='utf-8')

filepath = r"C:\Users\danat\Desktop\dvachbot\site_tgach\main.py"

with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

print("=== LINES 10110 to 10240 of site_tgach/main.py ===")
for idx in range(10109, min(10240, len(lines))):
    print(f"{idx+1:5d}: {lines[idx]}")

