import re

with open('site_tgach/importer.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if "async with db_lock, get_db_connection() as conn:" in line:
        indent = line[:len(line) - len(line.lstrip())]
        new_lines.append(indent + "async with get_db_connection() as conn:\n")
        new_lines.append(indent + "    async with db_lock:\n")
    else:
        new_lines.append(line)

with open('site_tgach/importer.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
