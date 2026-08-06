import ast
import importlib
import os
import sys

workspace = r"C:\Users\danat\Desktop\dvachbot"
os.chdir(workspace)
if workspace not in sys.path:
    sys.path.insert(0, workspace)

target_files = [
    "user_manager.py",
    "periodic_publisher.py",
    "broadcaster.py",
    "delivery_manager.py",
    "post_processor.py",
    "economy_extension.py",
    "admin_manager.py",
    "handlers/message_router.py",
    "site_tgach/importer.py",
    "site_tgach/mirror_worker.py",
    "site_tgach/main.py",
    "Dubsite_tgach/main.py",
    "main.py",
]

print("=== DEEP IMPORT & AST ANALYSIS ===")

import_issues = []
bare_except_files = []
empty_except_files = []

for rel_path in target_files:
    full_path = os.path.join(workspace, rel_path)
    print(f"\n--- Checking {rel_path} ---")
    with open(full_path, "r", encoding="utf-8") as f:
        source = f.read()
    
    tree = ast.parse(source, filename=rel_path)
    
    # Collect imports
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)

    # Check except handlers
    bare_count = 0
    empty_pass_count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                bare_count += 1
            if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                empty_pass_count += 1

    if bare_count > 0:
        bare_except_files.append((rel_path, bare_count))
    if empty_pass_count > 0:
        empty_except_files.append((rel_path, empty_pass_count))

    print(f"Imports found: {len(imports)}")
    print(f"Bare excepts: {bare_count}, Empty pass excepts: {empty_pass_count}")

    # Test importing top-level packages (without executing local script logic if possible)
    for mod in set(imports):
        top_mod = mod.split('.')[0]
        # Ignore local relative/project modules that aren't standalone packages unless in path
        try:
            importlib.util.find_spec(top_mod)
        except Exception as e:
            print(f"  [!] Cannot resolve module import: {mod} ({e})")
            import_issues.append((rel_path, mod, str(e)))

print("\n=== SUMMARY OF AST / EXCEPTION / IMPORT ANALYSIS ===")
print(f"Bare except occurrences across modified files: {bare_except_files}")
print(f"Empty pass except occurrences across modified files: {empty_except_files}")
print(f"Unresolvable import specifications: {len(import_issues)}")
for issue in import_issues:
    print("  Issue:", issue)
