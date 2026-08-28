import os
import re

def patch_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    if 'asyncio.create_task(' not in content:
        return False
        
    if 'from common.task_manager import spawn_task' in content:
        return False

    # Replace asyncio.create_task( with spawn_task(
    new_content = re.sub(r'\basyncio\.create_task\(', 'spawn_task(', content)
    
    if new_content != content:
        # Inject import
        lines = new_content.split('\n')
        for i, line in enumerate(lines):
            if line.startswith('import asyncio') or 'import asyncio' in line:
                lines.insert(i + 1, 'from common.task_manager import spawn_task')
                break
        else:
            # If no import asyncio found, put it at top after docstrings/shebangs
            for i, line in enumerate(lines):
                if line.strip() and not line.startswith('#') and not line.startswith('"""'):
                    lines.insert(i, 'from common.task_manager import spawn_task')
                    break
                    
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        return True
    return False

def main():
    modified = []
    for r, d, fs in os.walk('.'):
        if 'venv' in r or '__pycache__' in r or '.git' in r:
            continue
        for f in fs:
            if f.endswith('.py'):
                path = os.path.join(r, f)
                if patch_file(path):
                    modified.append(path)
                    
    print(f"Patched {len(modified)} files:")
    for m in modified:
        print(f"  - {m}")

if __name__ == '__main__':
    main()
