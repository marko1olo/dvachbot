import re

with open(r"C:\Users\danat\Desktop\dvachbot\common\database.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

current_func = "NONE"
func_locks = {}

for idx, line in enumerate(lines, 1):
    m = re.match(r"^(?:async\s+)?def\s+([a-zA-Z0-9_]+)\(", line)
    if m:
        current_func = m.group(1)
        func_locks[current_func] = {"has_db_lock": False, "has_db_sleep": False, "start_line": idx}
    
    if current_func != "NONE":
        if "db_lock" in line:
            func_locks[current_func]["has_db_lock"] = True
        if "db_sleep" in line:
            func_locks[current_func]["has_db_sleep"] = True

funcs_with_both = [k for k, v in func_locks.items() if v["has_db_lock"] and v["has_db_sleep"]]
funcs_with_sleep_only = [k for k, v in func_locks.items() if not v["has_db_lock"] and v["has_db_sleep"]]
funcs_with_lock_only = [k for k, v in func_locks.items() if v["has_db_lock"] and not v["has_db_sleep"]]

print(f"Functions with BOTH db_lock and db_sleep ({len(funcs_with_both)}): {funcs_with_both}")
print(f"Functions with db_sleep ONLY ({len(funcs_with_sleep_only)}): {funcs_with_sleep_only}")
print(f"Functions with db_lock ONLY ({len(funcs_with_lock_only)}): {funcs_with_lock_only}")
