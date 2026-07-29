import re
import os

files_to_check = [
    r"C:\Users\danat\Desktop\dvachbot\site_tgach\main.py",
    r"C:\Users\danat\Desktop\dvachbot\main.py",
]

# Check all py files in site_tgach
for root, dirs, files in os.walk(r"C:\Users\danat\Desktop\dvachbot\site_tgach"):
    for file in files:
        if file.endswith(".py"):
            full_path = os.path.join(root, file)
            if full_path not in files_to_check:
                files_to_check.append(full_path)

print(f"Checking {len(files_to_check)} python files...")

route_pattern = re.compile(r'@(?:app|router)\.(?:get|post|head|options|put|delete|api_route|route)\(\s*["\']([^"\']+)["\']')

for filepath in files_to_check:
    if not os.path.exists(filepath):
        continue
    rel = os.path.relpath(filepath, r"C:\Users\danat\Desktop\dvachbot")
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    
    matches = route_pattern.finditer(content)
    media_matches = []
    all_routes = []
    for m in matches:
        route_path = m.group(1)
        all_routes.append((m.start(), route_path))
        if any(k in route_path.lower() for k in ["file", "thumb", "i/", "preview", "media", "src", "img", "image", "photo", "video", "download", "stream"]):
            media_matches.append((m.start(), route_path))
    
    print(f"\n--- {rel} --- (Total routes: {len(all_routes)})")
    for start_pos, rpath in media_matches:
        # Get line number
        line_num = content[:start_pos].count('\n') + 1
        # Find function definition following the decorator
        func_match = re.search(r'(async\s+def|def)\s+([a_zA_Z0-9_]+)\s*\(', content[start_pos:start_pos+300])
        func_name = func_match.group(2) if func_match else "unknown"
        print(f"Line {line_num}: Route '{rpath}' -> function '{func_name}'")

