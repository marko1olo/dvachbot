import re
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

filepath = r"C:\Users\danat\Desktop\dvachbot\site_tgach\main.py"

with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

print(f"Total lines in site_tgach/main.py: {len(lines)}")

routes = []
for idx, line in enumerate(lines, 1):
    l = line.strip()
    if l.startswith("@app.") or l.startswith("@router."):
        if '"' in line or "'" in line:
            # Find next def statement
            def_line = ""
            for j in range(idx, min(idx + 10, len(lines))):
                if lines[j].strip().startswith("def ") or lines[j].strip().startswith("async def "):
                    def_line = lines[j].strip()
                    break
            routes.append((idx, l, def_line))

for idx, dec, func in routes:
    print(f"Line {idx:5d}: {dec} --> {func}")

