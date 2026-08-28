import os

for root, dirs, files in os.walk('C:/Users/danat/Desktop/dvachbot'):
    if 'venv' in root or '.git' in root: continue
    for file in files:
        if file.endswith('.py'):
            try:
                with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                    for i, line in enumerate(f):
                        # \u043a\u0430\u043b is кал, \u0431\u0430\u044f\u043d is баян
                        if '\u043a\u0430\u043b' in line.lower() or '\u0431\u0430\u044f\u043d' in line.lower():
                            if '\u0438\u0441\u043a\u0430\u043b' in line.lower() or '\u043b\u043e\u043a\u0430\u043b\u044c\u043d' in line.lower(): continue
                            print(f"{file}:{i+1} : {repr(line.strip())}")
            except Exception as e: pass
