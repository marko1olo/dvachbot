import ast
import os
import subprocess

def get_functions(file_content):
    try:
        tree = ast.parse(file_content)
    except Exception:
        return set()
    funcs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.add(node.name)
    return funcs

# Get main.py from HEAD
head_main = open('main_4days_ago.py', 'r', encoding='utf-16').read()
orig_funcs = get_functions(head_main)

current_funcs = set()
for root, _, files in os.walk('.'):
    if '.git' in root or 'venv' in root or 'scratch' in root or 'node_modules' in root:
        continue
    for file in files:
        if file.endswith('.py') and file != 'main_4days_ago.py' and file != 'compare_ast_functions.py' and file != 'audit_dead_code.py':
            f = os.path.join(root, file)
            content = open(f, 'r', encoding='utf-8-sig').read()
            funcs = get_functions(content)
            current_funcs.update(funcs)

missing = orig_funcs - current_funcs
extra = current_funcs - orig_funcs

import json
dump_data = {
    "orig": list(orig_funcs),
    "current": list(current_funcs),
    "missing": list(missing),
    "extra": list(extra)
}
with open('debug_sets.json', 'w', encoding='utf-8') as f:
    json.dump(dump_data, f, indent=2)

print("Dumped to debug_sets.json")
