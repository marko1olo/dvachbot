import glob
import re
import os

templates = sorted(glob.glob('site_tgach/templates/*.jinja2'))
print(f"Auditing {len(templates)} Jinja2 templates...\n")

total_issues = 0

for fpath in templates:
    with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    
    content = "".join(lines)
    
    # 1. Count </body> and </html>
    body_matches = [i+1 for i, line in enumerate(lines) if '</body>' in line.lower()]
    html_matches = [i+1 for i, line in enumerate(lines) if '</html>' in line.lower()]
    
    # 2. Extract IDs and find duplicates
    id_pattern = re.compile(r'id=["\']([^"\'\s{}]+)["\']')
    found_ids = {}
    dup_ids = {}
    
    for idx, line in enumerate(lines, 1):
        for m in id_pattern.finditer(line):
            elem_id = m.group(1)
            # Skip Jinja2 dynamic expressions in IDs like id="post-{{ id }}"
            if '{{' in elem_id or '}}' in elem_id:
                continue
            if elem_id in found_ids:
                if elem_id not in dup_ids:
                    dup_ids[elem_id] = [found_ids[elem_id]]
                dup_ids[elem_id].append(idx)
            else:
                found_ids[elem_id] = idx
                
    # 3. Check for tag syntax corruption/typos like <video clas<video class=
    typos = []
    typo_pattern = re.compile(r'<[a-zA-Z0-9]+\s+[^>]*<[a-zA-Z0-9]+')
    for idx, line in enumerate(lines, 1):
        if typo_pattern.search(line):
            typos.append((idx, line.strip()))
            
    # 4. Report
    file_issues = []
    if len(body_matches) > 1:
        file_issues.append(f"Multiple </body> tags found at lines: {body_matches}")
    if len(html_matches) > 1:
        file_issues.append(f"Multiple </html> tags found at lines: {html_matches}")
    if dup_ids:
        for elem_id, line_nums in dup_ids.items():
            file_issues.append(f"Duplicate ID '{elem_id}' at lines: {line_nums}")
    if typos:
        for line_num, snippet in typos:
            file_issues.append(f"Malformed tag typo at line {line_num}: {snippet}")
            
    if file_issues:
        total_issues += len(file_issues)
        print(f"[FAIL] {fpath}:")
        for iss in file_issues:
            print(f"  - {iss}")
    else:
        print(f"[OK] {fpath}")

print(f"\nTotal structural/markup issues found: {total_issues}")
