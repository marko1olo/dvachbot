import ast
import subprocess
import glob
import os

def clean_conflict_markers(content):
    lines = content.split('\n')
    cleaned = [line for line in lines if not (line.startswith('<<<<<<<') or line.startswith('=======') or line.startswith('>>>>>>>'))]
    return '\n'.join(cleaned)

def get_ast_from_git(commit, filename):
    try:
        content = subprocess.check_output(['git', 'show', f'{commit}:{filename}'], text=True, encoding='utf-8')
        content = clean_conflict_markers(content)
        return ast.parse(content)
    except Exception as e:
        print(f"Error reading {commit}:{filename}: {e}")
        return None

def get_ast_from_file(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return ast.parse(f.read())
    except Exception as e:
        # ignore parse errors on temp files
        return None

def extract_symbols(tree):
    if not tree:
        return set()
    symbols = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.add(node.name)
    return symbols

head_main_tree = get_ast_from_git('HEAD', 'main.py')
original_symbols = extract_symbols(head_main_tree)

current_all_symbols = set()
# Check all python files in the directory
for py_file in glob.glob('*.py'):
    if py_file.startswith('scratch_'):
        continue
    tree = get_ast_from_file(py_file)
    if tree:
        current_all_symbols |= extract_symbols(tree)

missing_symbols = original_symbols - current_all_symbols

print(f"Original symbols in main.py: {len(original_symbols)}")
print(f"Current symbols across all files: {len(current_all_symbols)}")
print(f"Missing symbols: {len(missing_symbols)}")

for sym in sorted(missing_symbols):
    print(f" - {sym}")
