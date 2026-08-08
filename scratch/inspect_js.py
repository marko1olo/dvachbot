from pathlib import Path

p = Path(r"C:\Users\danat\Desktop\dvachbot\site_tgach\static\js\main.src.js")
content = p.read_text(encoding='utf-8')
lines = content.splitlines()

def show_context(target, window=15):
    matches = [i for i, l in enumerate(lines) if target in l]
    out = []
    out.append(f"=== Matches for '{target}' ({len(matches)}) ===")
    for idx in matches:
        start = max(0, idx - window)
        end = min(len(lines), idx + window + 1)
        out.append(f"--- Line {idx+1} ---")
        for i in range(start, end):
            prefix = "->" if i == idx else "  "
            safe_line = lines[i].encode('ascii', errors='replace').decode('ascii')
            out.append(f"{prefix} {i+1}: {safe_line}")
    return "\n".join(out)

output = "\n\n".join([
    show_context("downloadCurrentFile"),
    show_context("showCurrentFileTags"),
    show_context("preload"),
    show_context("files/"),
    show_context("original_file_id")
])

Path(r"C:\Users\danat\Desktop\dvachbot\scratch\js_inspection.txt").write_text(output, encoding='utf-8')
print("Wrote JS inspection output to scratch/js_inspection.txt")
