import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def find_file_endpoints(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print(f"=== Searching Telegram file endpoints in {filepath} ===")
    lines = content.splitlines()
    for i, line in enumerate(lines, 1):
        if '/files/' in line or 'api.telegram.org' in line or 'RedirectResponse' in line or 'status_code=307' in line:
            print(f"Line {i}: {line.strip()}")

find_file_endpoints("site_tgach/main.py")
