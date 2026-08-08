from pathlib import Path

p = Path(r"C:\Users\danat\Desktop\dvachbot\site_tgach\static\js\main.src.js")
content = p.read_text(encoding='utf-8')
lines = content.splitlines()

def show_context(target, window=10):
    matches = [i for i, l in enumerate(lines) if target in l]
    print(f"=== Matches for '{target}' ({len(matches)}) ===")
    for idx in matches[:10]:
        start = max(0, idx - window)
        end = min(len(lines), idx + window + 1)
        print(f"--- Line {idx+1} ---")
        for i in range(start, end):
            prefix = "->" if i == idx else "  "
            safe = lines[i].encode('ascii', errors='replace').decode('ascii')
            print(f"{prefix} {i+1}: {safe}")

show_context("ImageViewer", 10)
show_context("openImageViewer", 10)
