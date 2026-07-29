import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

filepath = r"C:\Users\danat\Desktop\dvachbot\site_tgach\main.py"

with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
    content = f.read()

lines = content.splitlines()

print("=== ALL MIDDLEWARES IN site_tgach/main.py ===")
for idx, line in enumerate(lines, 1):
    if "@app.middleware" in line or "class " in line and "middleware" in line.lower():
        print(f"Line {idx:5d}: {line.strip()}")
        # print next 20 lines
        for k in range(idx, min(idx + 25, len(lines))):
            print(f"  {k+1:5d}: {lines[k]}")
        print("-" * 50)

