import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

filepath = r"C:\Users\danat\Desktop\dvachbot\site_tgach\main.py"

with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

print("Search for static mounts, custom file routes, preview routes, etc. in main.py:")

for idx, line in enumerate(lines, 1):
    l = line.lower()
    if any(k in l for k in ["/file", "/thumb", "/i/", "/preview", "/src/", "staticfiles", "mount", "get_telegram_file", "proxy", "stream", "media"]):
        if any(dec in line for dec in ["@app", "@router", "mount", "def ", "add_route"]):
            print(f"Line {idx:5d}: {line.strip()}")

