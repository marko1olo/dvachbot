import ast
import os
import re

target_files = ['post_helpers.py', 'bot_helpers.py', 'ai_manager.py', 'stats_manager.py']
repo_dir = r"C:\Users\danat\Desktop\dvachbot"

def get_funcs(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        return [node.name for node in ast.walk(ast.parse(content)) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    except Exception:
        return []

py_files = [os.path.join(r, f) for r, d, files in os.walk(repo_dir) for f in files if f.endswith('.py') and not any(x in r for x in ['.git', 'venv', 'node_modules', '__pycache__'])]

results = []
for target in target_files:
    funcs = get_funcs(os.path.join(repo_dir, target))
    for func in funcs:
        pattern = re.compile(r'\b' + re.escape(func) + r'\b')
        call_sites = []
        for py_file in py_files:
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if py_file.endswith(target) and f"def {func}" in line: continue
                        if pattern.search(line): call_sites.append(py_file)
            except Exception: pass
        if not call_sites:
            results.append(f"DEAD: {target} -> {func} NEVER called")
        elif all(c.endswith(target) for c in call_sites):
            results.append(f"INTERNAL ONLY (potential dead): {target} -> {func}")

print("\n".join(results))
