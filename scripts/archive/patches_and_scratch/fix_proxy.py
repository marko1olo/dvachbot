import os
import re

replacement = 'PROXY_URL = os.getenv("PROXY_URL") or os.getenv("HTTPS_PROXY") or "http://127.0.0.1:10808"'

files = [
    'site_tgach/importer.py',
    'site_tgach/main.py',
    'site_tgach/neuro_moderator.py',
    'site_tgach/neuro_poster.py',
    'site_tgach/tagging_worker.py'
]

for f in files:
    path = os.path.join(r'C:\Users\danat\Desktop\dvachbot', f)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Regex to match PROXY_URL = "http://127.0.0.1:10808" with any spacing
        new_content, num = re.subn(r'PROXY_URL\s*=\s*"http://127\.0\.0\.1:10808"', replacement, content)
        if num > 0:
            # Need to make sure os is imported, usually it is, let's just write
            with open(path, 'w', encoding='utf-8') as file:
                file.write(new_content)
            print(f'Fixed {f}')
        else:
            print(f'Target string not found in {f}')
    else:
        print(f'File {f} not found')
