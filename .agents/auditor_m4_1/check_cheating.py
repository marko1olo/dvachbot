import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

files = [
    'site_tgach/main.py',
    'common/database.py',
    'site_tgach/tagging_worker.py',
    'site_tgach/static/js/main.src.js',
    'site_tgach/static/js/main.js'
]

keywords = ['>>1234', '343717.html', '17683067552852', 'mock', 'fake', 'dummy_sha']

for path in files:
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    print('===', path, '===')
    for kw in keywords:
        matches = list(re.finditer(re.escape(kw), content))
        if matches:
            print(f'  Found keyword "{kw}": {len(matches)} occurrences')
            for m in matches[:5]:
                start = max(0, m.start() - 40)
                end = min(len(content), m.end() + 40)
                snippet = content[start:end].replace('\n', ' ')
                print(f'    ... {snippet} ...')
