import py_compile
import sys

files_to_check = [
    r"C:\Users\danat\Desktop\dvachbot\common\database.py",
    r"C:\Users\danat\Desktop\dvachbot\common\db_pool.py",
    r"C:\Users\danat\Desktop\dvachbot\main.py",
    r"C:\Users\danat\Desktop\dvachbot\common\bot_helpers.py",
]

for file_path in files_to_check:
    try:
        py_compile.compile(file_path, doraise=True)
        print(f"Syntax OK: {file_path}")
    except py_compile.PyCompileError as e:
        print(f"Syntax ERROR in {file_path}: {e}")
