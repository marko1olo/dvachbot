import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

files = [
    'common/text_utils.py',
    'site_tgach/main.py',
    'Dubsite_tgach/main.py',
    'site_tgach/static/js/main.src.js',
    'site_tgach/static/js/main.js'
]

patterns = [
    r'POST_LINK', r'URL_PATTERN', r'linkRegex', r'&gt;&gt;', r'>>', r'cleanUrlAndSuffix', r'sanitize_html', r'ALLOWED_TAGS_PATTERN'
]

for path in files:
    print('========================================')
    print('FILE:', path)
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    for i, line in enumerate(lines):
        if any(re.search(p, line) for p in patterns):
            print(f'{i+1}: {line.strip()[:140]}')
