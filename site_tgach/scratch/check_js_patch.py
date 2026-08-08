path = r'C:\Users\danat\Desktop\dvachbot\site_tgach\static\js\main.src.js'
with open(path, 'rb') as f:
    raw = f.read()

# Check around isVid block
idx = raw.find(b'} else if (isVid) {')
chunk = raw[idx:idx+1100].decode('utf-8', errors='replace')

import sys
sys.stdout.buffer.write(('Block at idx={}\n'.format(idx)).encode())
sys.stdout.buffer.write(chunk.encode('utf-8'))
sys.stdout.buffer.write(b'\n---END---\n')
sys.stdout.buffer.flush()
