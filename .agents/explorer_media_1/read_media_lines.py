import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

filepath = r"C:\Users\danat\Desktop\dvachbot\site_tgach\main.py"

with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
    content = f.read()
    lines = content.splitlines()

print("=== LINES 10100 to 10450 of site_tgach/main.py ===")
for idx in range(10100, min(10450, len(lines))):
    print(f"{idx+1:5d}: {lines[idx]}")

