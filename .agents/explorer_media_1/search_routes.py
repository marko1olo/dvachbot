import re
import os
import glob

search_dirs = [
    r"C:\Users\danat\Desktop\dvachbot\site_tgach",
    r"C:\Users\danat\Desktop\dvachbot"
]

patterns = [
    r"/(file|thumb|i|preview|media|src|img|image|video)[/\'\"]",
    r"@app\.(get|post|head|route|api_route)",
    r"@router\.(get|post|head|route|api_route)",
]

print("=== SEARCHING FOR MEDIA ROUTES IN PYTHON FILES ===")

for py_file in glob.glob(r"C:\Users\danat\Desktop\dvachbot\site_tgach\*.py") + [r"C:\Users\danat\Desktop\dvachbot\main.py"]:
    if not os.path.exists(py_file):
        continue
    rel_path = os.path.relpath(py_file, r"C:\Users\danat\Desktop\dvachbot")
    with open(py_file, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    for idx, line in enumerate(lines, 1):
        if any(term in line.lower() for term in ["/file/", "/thumb/", "/i/", "/preview/", "/media/"]):
            if "@app" in line or "@router" in line or "def " in line or "async def " in line or "route" in line:
                print(f"{rel_path}:{idx}: {line.strip()}")

