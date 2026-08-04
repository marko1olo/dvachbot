import re

def process_main():
    with open('main.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # We need to extract the functions and constants to move to delivery_manager.py
    extracted = []
    
    # 1. Constants
    const_patterns = [
        r'PRIORITY_PASSIVE_MEDIA_SLICE_SIZE\s*=\s*max\(.*?\)\n',
        r'PRIORITY_PRESSURE_PASSIVE_MEDIA_SLICE_SIZE\s*=\s*max\(.*?\)\n',
        r'PRIORITY_PASSIVE_SLICE_SIZE\s*=\s*max\(.*?\)\n',
        r'PRIORITY_PRESSURE_PASSIVE_SLICE_SIZE\s*=\s*max\(.*?\)\n',
        r'PRIORITY_PRESSURE_SLICE_AGE_SEC\s*=\s*max\(.*?\)\n',
    ]
    for p in const_patterns:
        m = re.search(p, content)
        if m:
            extracted.append(m.group(0))
            content = content.replace(m.group(0), '')

    # 2. Functions
    func_names = [
        '_queue_item_can_be_durable',
        '_durable_recipients_from_item',
        '_board_queue_oldest_age_sec',
        'get_board_activity_last_hours'
    ]
    
    for fname in func_names:
        # Find def or async def
        pattern = r'(?:async\s+)?def\s+' + fname + r'\b.*?:(?:\n\s+.*)*'
        # To make it safer, we match until the next def or class or end of file, but without consuming it
        # Actually, using a simple line-by-line parser for functions is safer.
        pass

    # Better function extractor
    lines = content.split('\n')
    new_lines = []
    in_func = False
    func_lines = []
    func_name = ''
    
    # Also remove global state variables
    remove_vars = ['is_shutting_down = False', 'drain_shutdown_requested = False', 
                   'durable_delivery_stats = {', 'weekly_active_users = {']
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Check global vars
        if any(line.startswith(v) for v in remove_vars):
            if line.startswith('durable_delivery_stats = {'):
                # Skip until }
                while i < len(lines) and not lines[i].startswith('}'):
                    i += 1
                i += 1
                continue
            i += 1
            continue

        # Check functions
        m = re.match(r'^(?:async\s+)?def\s+([a-zA-Z0-9_]+)\(', line)
        if m and m.group(1) in func_names:
            in_func = True
            func_name = m.group(1)
            func_lines = [line]
            i += 1
            while i < len(lines):
                if lines[i].startswith('def ') or lines[i].startswith('async def ') or lines[i].startswith('class '):
                    # Next top level block
                    break
                # Only append if it's indented or empty
                if not lines[i] or lines[i].startswith(' '):
                    func_lines.append(lines[i])
                elif lines[i].startswith('#') or lines[i].startswith('"""') or lines[i].startswith("'''"):
                    func_lines.append(lines[i])
                elif lines[i].startswith('@'):
                    func_lines.append(lines[i])
                else:
                    # End of function
                    break
                i += 1
            extracted.append('\n'.join(func_lines) + '\n')
            in_func = False
            continue
            
        new_lines.append(line)
        i += 1
        
    with open('main.py', 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_lines))
        
    return '\n'.join(extracted)

def update_delivery_manager(extracted_code):
    with open('delivery_manager.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Append extracted code to the top after imports
    # Let's add it right after the imports block (we can just put it at the end of the file, or somewhere safe)
    # The imports we need to add to delivery_manager.py:
    new_imports = """
from shared_state import (
    storage_lock, post_to_messages, is_shutting_down, drain_shutdown_requested, 
    durable_delivery_stats, weekly_active_users, BroadcastConfig, enqueue_board_message
)
from common.database import (
    upsert_delivery_queue_item, delete_delivery_queue_item, get_post_copies, 
    create_post, update_post_content, get_stream_active_users
)
from common.board_config import BOARD_CONFIG
from post_helpers import format_header
from help_text import HELP_TEXT_EN_COMMANDS, THREAD_PROMO_TEXT_EN
from datetime import timezone
UTC = timezone.utc

"""
    # Insert new imports after the first few lines
    lines = content.split('\n')
    import_idx = 0
    for i, line in enumerate(lines):
        if line.startswith('import ') or line.startswith('from '):
            import_idx = i
    
    # We will just prepend new imports and extracted code
    new_content = new_imports + extracted_code + "\n" + content
    
    with open('delivery_manager.py', 'w', encoding='utf-8') as f:
        f.write(new_content)

extracted = process_main()
update_delivery_manager(extracted)
print("Extracted and updated successfully!")
