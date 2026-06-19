import re
import os
import sys

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    path = r'C:\Users\danat\Documents\ввв.txt'
    if not os.path.exists(path):
        print("Log file not found.")
        return
        
    print(f"Analyzing {path}...")
    
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
        
    print(f"Total lines in log: {len(lines)}")
    
    # We will search for FloodWait messages and other statistics
    floodwait_lines = []
    for idx, line in enumerate(lines):
        if "FloodWait" in line or "пауза" in line:
            floodwait_lines.append((idx, line.strip()))
            
    print(f"Total FloodWait / pause lines: {len(floodwait_lines)}")
    if floodwait_lines:
        print("\nFirst 10 FloodWait occurrences:")
        for idx, line in floodwait_lines[:10]:
            print(f"  Line {idx}: {line}")
        print("\nLast 10 FloodWait occurrences:")
        for idx, line in floodwait_lines[-10:]:
            print(f"  Line {idx}: {line}")
            
    # Let's see the range of post numbers mentioned in the logs
    post_nums = []
    for line in lines:
        match = re.search(r'#(\d+)', line)
        if match:
            post_nums.append(int(match.group(1)))
            
    if post_nums:
        print(f"\nPost numbers range in logs: {min(post_nums)} to {max(post_nums)}")
        
    # Let's check if there are timestamps in the file (like HH:MM:SS or dates)
    has_timestamp = False
    for line in lines[:20]:
        if re.search(r'\d{2}:\d{2}:\d{2}', line) or re.search(r'\d{4}-\d{2}-\d{2}', line):
            has_timestamp = True
            print(f"Found timestamp sample: {line.strip()}")
            break
    if not has_timestamp:
        print("No standard date/time pattern found in the first 20 lines of the log.")

if __name__ == '__main__':
    main()
