import re
from pathlib import Path

templates_dir = Path(r"C:\Users\danat\Desktop\dvachbot\site_tgach\templates")
for p in sorted(templates_dir.glob("*.jinja2")):
    content = p.read_text(encoding="utf-8")
    for i, line in enumerate(content.splitlines(), 1):
        if "original_url" in line or "thumbnail_url" in line or "catbox.moe" in line:
            # print cleanly
            safe_line = line.strip().encode('ascii', errors='replace').decode('ascii')
            print(f"{p.name}:{i}: {safe_line}")
