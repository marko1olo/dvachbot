import compileall
import os
import io
import sys

workspace = r"C:\Users\danat\Desktop\dvachbot"
os.chdir(workspace)

failed_files = []

def walk_and_compile(dir_path, depth=0):
    if depth > 5:
        return
    for item in os.listdir(dir_path):
        if item in ('venv', '.git', '__pycache__', '.pytest_cache', '.mypy_cache'):
            continue
        full_path = os.path.join(dir_path, item)
        if os.path.isdir(full_path):
            walk_and_compile(full_path, depth + 1)
        elif item.endswith('.py'):
            try:
                ok = compileall.compile_file(full_path, quiet=1)
                if not ok:
                    failed_files.append(full_path)
            except Exception as e:
                failed_files.append((full_path, str(e)))

walk_and_compile('.')
print(f"Failed files count (excluding venv/.git): {len(failed_files)}")
for f in failed_files:
    print("FAILED:", f)
