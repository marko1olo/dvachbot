import sys
import re

with open(r'C:\Users\danat\Desktop\dvachbot\site_tgach\main.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

queries = [
    "_get_shared_aiohttp_session",
    "_mark_random_dead_file",
    "get_cached_file_path",
    "/file/",
    "/thumb/",
    "/i/",
    "/preview/",
    "Access-Control-Allow-Origin",
    "RedirectResponse",
    "StreamingResponse"
]

for q in queries:
    print(f"=== SEARCH FOR: {q} ===")
    matches = []
    for idx, line in enumerate(lines, 1):
        if q in line:
            matches.append((idx, line.strip()))
    for idx, text in matches[:30]:
        print(f"Line {idx}: {text}")
    print()
