"""
Scan for unbounded cache growth patterns in main.py.
Look for dicts/deques without .maxlen or without trimming logic.
"""
import re, sys

path = r'C:\Users\danat\Desktop\dvachbot\main.py'
with open(path, encoding='utf-8', errors='replace') as f:
    content = f.read()
    lines = content.splitlines()

# Known cache variables from prior analysis
CACHE_VARS = [
    'messages_storage',
    'CAPTCHA_SESSIONS', 
    'USER_MESSAGES',
    'contextual_reply_tracker',
    'contextual_reply_stats',
    'mode_cooldown_tracker',
    'board_data',
    'user_data_cache',
    'user_warn_cache',
    'thread_locks',
    'active_bans',
    '_failed_media_cache',
    'FailedMediaCache',
    'MUTE_CACHE',
]

sys.stdout.buffer.write(b'=== Cache Unbounded Growth Check ===\n')

for var in CACHE_VARS:
    # Find declaration
    decl_matches = [(i+1, lines[i]) for i in range(len(lines)) if re.search(rf'\b{var}\b\s*=\s*', lines[i]) and not lines[i].strip().startswith('#')]
    # Find maxsize/maxlen/trim/pop/clear references
    bound_matches = [i+1 for i in range(len(lines)) if re.search(rf'\b{var}\b', lines[i]) and re.search(r'maxsize|maxlen|\.pop\(|trim|evict|clear\(\)|deque\(|LRU|lru_cache', lines[i])]
    
    status = 'BOUNDED' if bound_matches else 'UNBOUNDED?'
    decl_lines = [f'L{ln}' for ln, _ in decl_matches[:2]]
    sys.stdout.buffer.write(f'{status:12} {var} (decl:{",".join(decl_lines) or "N/A"}, bound_refs:{bound_matches[:3]})\n'.encode('utf-8'))

sys.stdout.buffer.flush()
