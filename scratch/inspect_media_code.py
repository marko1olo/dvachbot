import json

def extract_lines(filepath, start, end, outpath):
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    snippet = "".join([f"{i+1}: {lines[i]}" for i in range(start-1, min(end, len(lines)))])
    with open(outpath, "w", encoding="utf-8") as out:
        out.write(snippet)
    print(f"Extracted lines {start}-{end} from {filepath} to {outpath}")

if __name__ == "__main__":
    extract_lines("site_tgach/static/js/main.src.js", 11240, 11600, "scratch/js_media_rescue.js")
    extract_lines("site_tgach/static/js/main.src.js", 14340, 14550, "scratch/js_smart_loader.js")
    extract_lines("site_tgach/main.py", 3340, 3700, "scratch/py_mirror_select.py")
