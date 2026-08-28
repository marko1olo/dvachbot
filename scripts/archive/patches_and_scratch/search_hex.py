import os
for root, dirs, files in os.walk('C:/Users/danat/Desktop/dvachbot'):
    if 'venv' in root or '.git' in root: continue
    for file in files:
        if file.endswith('.py'):
            try:
                with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                    for i, line in enumerate(f):
                        if '???' in line.lower() or '????' in line.lower():
                            if '?????' in line.lower() or '???????' in line.lower(): continue
                            print(f'{file}:{i+1} : {repr(line.strip())}')
            except Exception as e: pass
