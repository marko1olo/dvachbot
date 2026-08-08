import os
import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

for root, dirs, files in os.walk('.'):
    if 'venv' in root or '.git' in root:
        continue
    for file in files:
        if 'dub' in file.lower() or 'dub' in root.lower():
            print(os.path.join(root, file))
