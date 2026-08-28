import sys, os
sys.stdout.reconfigure(encoding='utf-8')
for root, _, files in os.walk('C:/Users/danat/Desktop/dvachbot'):
    if 'venv' in root or '.git' in root: continue
    for f in files:
        if f.endswith('.py'):
            try:
                for i, line in enumerate(open(f'{root}/{f}', encoding='utf-8')):
                    lower = line.lower()
                    if '"кал"' in lower or '"баян"' in lower or "'кал'" in lower or "'баян'" in lower:
                        print(f'{f}:{i+1} {repr(line.strip())}')
            except: pass
