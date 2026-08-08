import os, ast

for root, dirs, files in os.walk('.'):
    if 'venv' in root or '.git' in root or 'scratch' in root: continue
    for f in files:
        if f.endswith('.py'):
            path = os.path.join(root, f)
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as fp:
                    content = fp.read()
                if 'PostFiles' in content:
                    print(f"PostFiles in {path}")
            except Exception: pass
