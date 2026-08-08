path = r'C:\Users\danat\Desktop\dvachbot\site_tgach\static\js\main.src.js'
with open(path, 'rb') as f:
    raw = f.read()

content = raw.decode('utf-8', errors='replace')

import re, sys

# Find all catalog-thumb creation points
catalog_matches = [(m.start(), content[max(0,m.start()-20):m.start()+300]) 
                   for m in re.finditer(r'catalog-thumb lazy-media-wrapper', content)]

sys.stdout.buffer.write(f'catalog-thumb lazy-media-wrapper occurrences: {len(catalog_matches)}\n'.encode())
for i, (pos, ctx) in enumerate(catalog_matches):
    line_num = content[:pos].count('\n') + 1
    sys.stdout.buffer.write(f'\n[{i}] line~{line_num}, pos={pos}:\n'.encode())
    sys.stdout.buffer.write(ctx[:250].encode('utf-8'))
    sys.stdout.buffer.write(b'\n')
sys.stdout.buffer.flush()
