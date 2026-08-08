import urllib.request, sys

req = urllib.request.Request('http://127.0.0.1:8000/b/catalog')
with urllib.request.urlopen(req) as r:
    html = r.read().decode('utf-8', errors='replace')

sys.stdout.buffer.write(f'HTML length: {len(html)}\n'.encode())

# Find catalog-grid or catalog-item
import re
grid = re.search(r'catalog-grid', html)
items = list(re.finditer(r'catalog-item', html))
sys.stdout.buffer.write(f'catalog-grid found: {bool(grid)}\n'.encode())
sys.stdout.buffer.write(f'catalog-item found: {len(items)} times\n'.encode())

# Show first 500 chars of body
body_start = html.find('<body')
if body_start >= 0:
    sys.stdout.buffer.write(('Body start: ...' + html[body_start:body_start+500]).encode('utf-8'))
sys.stdout.buffer.flush()
