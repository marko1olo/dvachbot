import os
for root, dirs, files in os.walk('C:\\Users\\danat\\Desktop\\dvachbot'):
    for file in files:
        if file.endswith('.py'):
            try:
                with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    for i, line in enumerate(lines):
                        if '???' in line.lower() or '????' in line.lower():
                            # Only print if surrounded by quotes
                            if '\"???\"' in line.lower() or \"'???'\" in line.lower() or '\"????\"' in line.lower() or \"'????'\" in line.lower():
                                print(f'{os.path.join(root, file)}:{i+1}:{line.strip()}')
            except: pass
