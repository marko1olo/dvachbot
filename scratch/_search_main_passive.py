with open('main.py', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

for idx, line in enumerate(lines):
    if 'passive' in line.lower() or 'slice' in line.lower():
        print(f"Line {idx+1}: {line.strip()[:100]}")
