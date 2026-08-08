import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def check_file(filepath):
    print(f"=== Checking {filepath} ===")
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    for idx, line in enumerate(lines, 1):
        if 'sleep' in line:
            print(f"Line {idx}: {line.strip()}")

if __name__ == "__main__":
    check_file(r"C:\Users\danat\Desktop\dvachbot\common\db_pool.py")
    check_file(r"C:\Users\danat\Desktop\dvachbot\common\database.py")
