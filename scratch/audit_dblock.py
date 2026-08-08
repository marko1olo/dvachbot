"""
Scan main.py for Telegram API calls inside db_lock blocks.
A db_lock block starts at 'async with db_lock:' and ends when indentation drops back.
We look for bot. / tg_api / send_message / send_photo inside such blocks.
"""
import re, sys

path = r'C:\Users\danat\Desktop\dvachbot\main.py'
with open(path, encoding='utf-8', errors='replace') as f:
    lines = f.readlines()

DANGER_PATTERNS = re.compile(
    r'(await\s+bot\.|await\s+tg_api\.|\.send_message|\.send_photo|\.send_video|'
    r'\.send_document|\.send_audio|\.forward_message|\.answer_callback|'
    r'await\s+message\.reply|await\s+message\.answer|await\s+asyncio\.sleep)'
)
DB_LOCK_OPEN = re.compile(r'async with (?:db_lock|ctx\.db_lock):')

issues = []
in_lock = False
lock_indent = -1
lock_start_line = -1

for i, line in enumerate(lines, 1):
    stripped = line.rstrip()
    indent = len(line) - len(line.lstrip())
    
    if DB_LOCK_OPEN.search(stripped):
        in_lock = True
        lock_indent = indent
        lock_start_line = i
        continue
    
    if in_lock:
        # Exit lock when indent drops back to lock level or less (non-empty lines)
        if stripped and indent <= lock_indent and not stripped.lstrip().startswith('#'):
            in_lock = False
            lock_indent = -1
            lock_start_line = -1
        else:
            if DANGER_PATTERNS.search(stripped):
                issues.append((lock_start_line, i, stripped.strip()))

sys.stdout.buffer.write(f'Dangerous calls inside db_lock: {len(issues)}\n'.encode())
for lock_ln, call_ln, code in issues:
    sys.stdout.buffer.write(f'  lock_opened@L{lock_ln}, call@L{call_ln}: {code[:120]}\n'.encode('utf-8'))
sys.stdout.buffer.flush()
