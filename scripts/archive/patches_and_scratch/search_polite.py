import os
import re

keywords = r"(?i)(пожалуйста|извини|к сожалению|успешно|спасибо)"
pattern = re.compile(keywords)

results = []
for root, dirs, files in os.walk('.'):
    if 'venv' in root or '.git' in root or '__pycache__' in root:
        continue
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                for i, line in enumerate(f):
                    if pattern.search(line):
                        results.append(f"{filepath}:{i+1}: {line.strip()}")

with open('search_polite.txt', 'w', encoding='utf-8') as f:
    for r in results:
        f.write(r + '\n')
