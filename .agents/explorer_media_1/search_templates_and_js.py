import os
import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

project_dir = r"C:\Users\danat\Desktop\dvachbot"

media_terms = ["/file/", "/thumb/", "/i/", "/preview/", "/files/", "/src/"]

matches_found = []

for root, dirs, files in os.walk(project_dir):
    if ".git" in root or ".venv" in root or "venv" in root or "__pycache__" in root:
        continue
    for file in files:
        if file.endswith((".py", ".html", ".jinja2", ".js", ".css", ".conf", ".nginx", ".sh", ".bat", ".md")):
            filepath = os.path.join(root, file)
            rel = os.path.relpath(filepath, project_dir)
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                for idx, line in enumerate(f, 1):
                    for term in media_terms:
                        if term in line:
                            matches_found.append((rel, idx, term, line.strip()[:140]))

print(f"Total matches found across project: {len(matches_found)}")
for rel, idx, term, snippet in matches_found[:50]:
    print(f"{rel}:{idx} [{term}]: {snippet}")

