import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def inspect_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print(f"=== Inspecting {filepath} ===")
    lines = content.splitlines()
    for i, line in enumerate(lines, 1):
        if 'db_sleep' in line or 'asyncio.sleep' in line:
            print(f"Line {i}: {line.strip()}")

inspect_file("common/db_pool.py")
inspect_file("common/database.py")
inspect_file("site_tgach/tagging_worker.py")
