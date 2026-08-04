import os

lines = open('main.py', encoding='utf-8').readlines()
func_lines = []
new_lines = []
in_func = False

for l in lines:
    if l.startswith('def clean_html_for_tg') and not in_func:
        in_func = True
        func_lines.append(l)
    elif in_func and (l.startswith(' ') or not l.strip()):
        func_lines.append(l)
    elif in_func:
        in_func = False
        new_lines.append(l)
    else:
        new_lines.append(l)

open('main.py', 'w', encoding='utf-8').write(''.join(new_lines))
open('common/text_utils.py', 'a', encoding='utf-8').write('\n' + ''.join(func_lines))
print("Extracted successfully.")
