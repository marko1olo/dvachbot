from pathlib import Path

p = Path(r"C:\Users\danat\Desktop\dvachbot\site_tgach\static\js\main.src.js")
content = p.read_text(encoding='utf-8')

for i, line in enumerate(content.splitlines(), 1):
    if "original_url" in line or "thumbnail_url" in line:
        safe = line.strip().encode('ascii', errors='replace').decode('ascii')
        print(f"Line {i}: {safe}")
