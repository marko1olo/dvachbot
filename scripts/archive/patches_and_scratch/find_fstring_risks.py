import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

with open('main.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

problems = []
for i, line in enumerate(lines, 1):
    s = line.strip()
    has_answer_f = '.answer(f"' in s or ".answer(f'" in s
    has_edit_f = '.edit_text(f"' in s or ".edit_text(f'" in s
    has_send_f = '.send_message(f"' in s or ".send_message(f'" in s
    
    if (has_answer_f or has_edit_f or has_send_f) and '{' in s and '}' in s:
        if 'parse_mode' not in s and 'escape_html' not in s:
            problems.append((i, s[:200]))

for num, ctx in problems:
    print(f'LINE {num}: {ctx}')
print(f'\nTotal: {len(problems)}')
