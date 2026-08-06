import re

target = r"C:\Users\danat\Desktop\dvachbot\main.py"
with open(target, "r", encoding="utf-8") as f:
    lines = f.readlines()

globals_found = []
for i, line in enumerate(lines):
    if re.match(r'^[A-Za-z0-9_]+\s*=\s*(dict|defaultdict|set|list|\[\]|\{\})', line):
        globals_found.append(f"Line {i+1}: {line.strip()}")
    elif re.match(r'^(user_states|board_data|GLOBAL_BOTS|delivery_queue|active_sessions|current_media_groups)', line):
        globals_found.append(f"Line {i+1}: {line.strip()}")

with open("scratch/globals.txt", "w", encoding="utf-8") as out:
    for g in globals_found:
        out.write(g + "\n")
