import os, re

def search_weak_spots():
    patterns = r'(subprocess\.Popen|subprocess\.run|asyncio\.create_task|ClientSession|openai|requests\.get|httpx)'
    with open('weak_spots.txt', 'w', encoding='utf-8') as out:
        for r, d, fs in os.walk('.'):
            if 'venv' in r or '__pycache__' in r or '.git' in r:
                continue
            for f in fs:
                if not f.endswith('.py'):
                    continue
                path = os.path.join(r, f)
                try:
                    with open(path, 'r', encoding='utf-8', errors='ignore') as src:
                        for i, line in enumerate(src):
                            if re.search(patterns, line, re.IGNORECASE):
                                out.write(f"{path}:{i+1}:{line.strip()}\n")
                except Exception as e:
                    pass

if __name__ == '__main__':
    search_weak_spots()
