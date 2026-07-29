import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

main_path = r"C:\Users\danat\Desktop\dvachbot\site_tgach\main.py"
with open(main_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

for idx, line in enumerate(lines, 1):
    if "_proxy_external_url" in line:
        print(f"Line {idx}: {line.strip()}")
