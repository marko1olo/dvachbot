import os
import re
import glob

pattern = re.compile(r'(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER)\s+.*?(?=;|\'\'\'|"""|\n\n)', re.DOTALL | re.IGNORECASE)

results = []

for root, dirs, files in os.walk(r'C:\Users\danat\Desktop\dvachbot'):
    if 'venv' in root or '.git' in root or '.agents' in root or '__pycache__' in root:
        continue
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                matches = re.finditer(r'(?:SELECT|INSERT|UPDATE|DELETE)\s+[^"\']*(?:From|Into|Set|Where|JOIN)[^"\']*', content, re.IGNORECASE)
                for line_no, line in enumerate(content.splitlines(), 1):
                    if any(kw in line.upper() for kw in ['SELECT ', 'INSERT ', 'UPDATE ', 'DELETE ']):
                        results.append(f"{os.path.relpath(filepath, r'C:\Users\danat\Desktop\dvachbot')}:{line_no}: {line.strip()}")

with open(r'C:\Users\danat\Desktop\dvachbot\.agents\explorer_2\sql_lines.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))

print(f"Found {len(results)} SQL query lines.")
