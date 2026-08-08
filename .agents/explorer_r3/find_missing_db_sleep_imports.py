import re

with open(r"C:\Users\danat\Desktop\dvachbot\common\database.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

# Check top level imports
top_has_db_sleep = False
for line in lines[:50]:
    if "db_sleep" in line and "import" in line:
        top_has_db_sleep = True

print(f"Module-level db_sleep import present: {top_has_db_sleep}")

current_func = "MODULE_LEVEL"
func_has_local_db_sleep_import = False
func_uses_db_sleep = False
func_start_line = 0

missing_imports = []

for idx, line in enumerate(lines, 1):
    m = re.match(r"^\s*(?:async\s+)?def\s+([a-zA-Z0-9_]+)\(", line)
    if m:
        if current_func != "MODULE_LEVEL" and func_uses_db_sleep:
            if not (top_has_db_sleep or func_has_local_db_sleep_import):
                missing_imports.append((func_start_line, current_func))
        
        current_func = m.group(1)
        func_start_line = idx
        func_has_local_db_sleep_import = False
        func_uses_db_sleep = False

    if "db_sleep" in line:
        if "import" in line:
            func_has_local_db_sleep_import = True
        else:
            func_uses_db_sleep = True

# Check last function
if current_func != "MODULE_LEVEL" and func_uses_db_sleep:
    if not (top_has_db_sleep or func_has_local_db_sleep_import):
        missing_imports.append((func_start_line, current_func))

print(f"\nFunctions that call db_sleep WITHOUT importing it ({len(missing_imports)}):")
for start_line, func_name in missing_imports:
    print(f"Line {start_line:4d}: {func_name}")
