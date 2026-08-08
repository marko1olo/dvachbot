path = r'C:\Users\danat\Desktop\dvachbot\site_tgach\static\js\main.src.js'
with open(path, 'rb') as f:
    raw = f.read()

content = raw.decode('utf-8', errors='replace')

# Find ALL occurrences of poster= in the file
import re
matches = [(m.start(), m.group(0), content[max(0,m.start()-80):m.start()+120]) 
           for m in re.finditer(r'poster=', content)]

import sys
sys.stdout.buffer.write(f'Total poster= occurrences: {len(matches)}\n'.encode())
for i, (pos, match, ctx) in enumerate(matches):
    sys.stdout.buffer.write(f'\n[{i}] pos={pos}:\n{ctx}\n'.encode('utf-8'))
sys.stdout.buffer.flush()
