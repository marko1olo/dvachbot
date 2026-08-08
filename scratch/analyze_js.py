import re

def search_in_file(filepath, keywords):
    print(f"=== Searching in {filepath} ===")
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    for idx, line in enumerate(lines, 1):
        for kw in keywords:
            if kw.lower() in line.lower():
                print(f"Line {idx}: {line.strip()[:140]}")
                break

if __name__ == "__main__":
    search_in_file("site_tgach/static/js/main.src.js", ["MediaRescue", "FailedMediaCache", "createMediaElement", "renderPost", "catbox", "lazy", "skip="])
    print("\n")
    search_in_file("site_tgach/main.py", ["/files/", "/api/media", "catbox", "proxy", "is_broken", "thumbnail_url"])
