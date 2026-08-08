import os

file_path = 'user_manager.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

if 'from post_helpers import format_header' not in content:
    lines = content.split('\n')
    # Find the last import statement
    import_idx = 0
    for i, line in enumerate(lines):
        if line.startswith('import ') or line.startswith('from '):
            import_idx = i
    
    # Insert after the last import
    lines.insert(import_idx + 1, 'from post_helpers import format_header')
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print("Added format_header import to user_manager.py")
else:
    print("format_header already imported in user_manager.py")
