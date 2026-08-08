from pathlib import Path

p = Path(r"C:\Users\danat\Desktop\dvachbot\site_tgach\static\js\main.src.js")
content = p.read_text(encoding='utf-8')
lines = content.splitlines()

for i, l in enumerate(lines, 1):
    if "file-thumb" in l or "gallery-trigger" in l or "modal" in l.lower() and "image" in l.lower():
        safe = l.encode('ascii', errors='replace').decode('ascii')
        print(f"{i}: {safe}")
