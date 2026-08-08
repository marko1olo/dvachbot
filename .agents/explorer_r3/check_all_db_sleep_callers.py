import re

with open(r"C:\Users\danat\Desktop\dvachbot\common\database.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

call_sites = []

for idx, line in enumerate(lines, 1):
    if "db_sleep" in line and not line.strip().startswith("#"):
        # Look backwards to find the enclosing function definition and whether 'async with db_lock' precedes it
        func_name = "UNKNOWN"
        has_lock_in_func = False
        has_lock_before = False
        
        # Scan backward up to 100 lines
        for i in range(idx - 1, max(0, idx - 150), -1):
            l = lines[i]
            if "async with db_lock" in l:
                has_lock_before = True
            m = re.match(r"^\s*(?:async\s+)?def\s+([a-zA-Z0-9_]+)\(", l)
            if m:
                func_name = m.group(1)
                break
        
        call_sites.append((idx, func_name, has_lock_before, line.strip()))

print(f"Total db_sleep call sites: {len(call_sites)}")
no_lock_calls = [c for c in call_sites if not c[2]]

print(f"\nCall sites WITHOUT preceding 'async with db_lock' in function ({len(no_lock_calls)}):")
for idx, func, has_lock, code in no_lock_calls:
    print(f"Line {idx} in {func}: {code}")
