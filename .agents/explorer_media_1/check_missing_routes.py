import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

filepath = r"C:\Users\danat\Desktop\dvachbot\site_tgach\main.py"

with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
    content = f.read()

patterns = [
    r'/file/\{',
    r'/thumb/\{',
    r'/i/\{',
    r'/preview/\{',
    r'/src/\{',
    r'"/file/',
    r'"/thumb/',
    r'"/i/',
    r'"/preview/',
    r'"/src/',
    r"'/file/",
    r"'/thumb/",
    r"'/i/",
    r"'/preview/",
    r"'/src/",
]

print("Searching for /file/, /thumb/, /i/, /preview/, /src/ endpoint decorators or path matches:")
for p in patterns:
    matches = list(re.finditer(p, content))
    print(f"Pattern '{p}': {len(matches)} matches")
    for m in matches[:10]:
        line_num = content[:m.start()].count('\n') + 1
        line = content.splitlines()[line_num-1].strip()
        print(f"  Line {line_num}: {line[:120]}")

