import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def search_imports(root_dir):
    for root, dirs, files in os.walk(root_dir):
        if '.git' in root or '__pycache__' in root or '.venv' in root or '.agents' in root or 'scratch' in root:
            continue
        for f in files:
            if f.endswith('.py'):
                path = os.path.join(root, f)
                with open(path, 'r', encoding='utf-8', errors='ignore') as file:
                    content = file.read()
                    if 'db_pool' in content:
                        for idx, line in enumerate(content.splitlines(), 1):
                            if 'db_pool' in line:
                                print(f"{path}:{idx}: {line.strip()}")

search_imports(r"C:\Users\danat\Desktop\dvachbot")
