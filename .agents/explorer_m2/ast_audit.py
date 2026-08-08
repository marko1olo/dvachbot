import ast
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
root = r'C:\Users\danat\Desktop\dvachbot'

def check_file(fpath):
    rel = os.path.relpath(fpath, root)
    with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
        code = f.read()
    try:
        tree = ast.parse(code, filename=fpath)
    except SyntaxError as e:
        print(f'SyntaxError in {rel}: {e}')
        return

    has_def = False
    has_import = False
    has_star_import_post_helpers = False

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == 'format_header':
                has_def = True
        elif isinstance(node, ast.ImportFrom):
            if node.module == 'post_helpers':
                for alias in node.names:
                    if alias.name == 'format_header':
                        has_import = True
                    if alias.name == '*':
                        has_star_import_post_helpers = True

    references = []
    class Visitor(ast.NodeVisitor):
        def visit_Name(self, node):
            if node.id == 'format_header':
                references.append(node.lineno)
            self.generic_visit(node)

    Visitor().visit(tree)

    if references:
        is_safe = has_def or has_import or has_star_import_post_helpers
        status = 'DEFINED' if has_def else ('IMPORTED' if has_import else ('STAR_IMPORTED' if has_star_import_post_helpers else 'UNBOUND/MISSING'))
        print(f'{rel}: {len(references)} refs to format_header. Status: {status} (safe={is_safe})')
        if not is_safe:
            print(f'  --> DANGER: Potential NameError in {rel} at lines: {references}')

for dirpath, dirnames, filenames in os.walk(root):
    if 'venv' in dirpath or '.agents' in dirpath or '.git' in dirpath:
        continue
    for fname in filenames:
        if fname.endswith('.py'):
            check_file(os.path.join(dirpath, fname))
