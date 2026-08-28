import os
with open('search_out.txt', 'w', encoding='utf-8') as out:
    for root, dirs, files in os.walk('C:/Users/danat/Desktop/dvachbot'):
        if 'venv' in root or '.git' in root or '.venv' in root: continue
        for file in files:
            if file.endswith('.py'):
                try:
                    with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                        for i, line in enumerate(f):
                            low = line.lower()
                            if '???' in low or '????' in low:
                                if '?????' in low or '???????' in low: continue
                                out.write(f'{os.path.join(root, file)}:{i+1}:{line.strip()}\n')
                except: pass
