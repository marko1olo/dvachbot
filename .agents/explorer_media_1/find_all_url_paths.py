import sys
import os
import re

sys.stdout.reconfigure(encoding='utf-8')

project_dir = r"C:\Users\danat\Desktop\dvachbot"

keywords = ["/file/", "/thumb/", "/i/", "/preview/", "/src/", "/files/", "files/"]

for root, dirs, files in os.walk(os.path.join(project_dir, "site_tgach")):
    for file in files:
        if file.endswith(".py"):
            filepath = os.path.join(root, file)
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                for idx, line in enumerate(f, 1):
                    if any(k in line for k in keywords):
                        rel = os.path.relpath(filepath, project_dir)
                        print(f"{rel}:{idx}: {line.strip()[:140]}")

