import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def inspect_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print(f"=== Inspecting {filepath} ===")
    lines = content.splitlines()
    for i, line in enumerate(lines, 1):
        if 'format_header' in line:
            print(f"Line {i}: {line.strip()}")

inspect_file("user_manager.py")
inspect_file("main.py")
inspect_file("site_tgach/main.py")
