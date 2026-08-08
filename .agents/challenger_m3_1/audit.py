import os
import re
import sys

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

root_dir = r"C:\Users\danat\Desktop\dvachbot"

print("=== AUDITING R1: Telegram file endpoints in site_tgach/main.py ===")
main_py_path = os.path.join(root_dir, "site_tgach", "main.py")
with open(main_py_path, "r", encoding="utf-8") as f:
    main_content = f.read()

# Find occurrences of 307 or file endpoints in main.py
lines = main_content.splitlines()
for idx, line in enumerate(lines, 1):
    if "/files/" in line or "/file/" in line or "307" in line or "RedirectResponse" in line:
        if "def " in line or "RedirectResponse" in line or "@app" in line or "api.telegram.org" in line:
            print(f"Line {idx}: {line}")

# Search for functions with file endpoints
print("\n--- Detailed File Endpoint Search in site_tgach/main.py ---")
file_endpoint_blocks = []
in_block = False
current_block = []
for idx, line in enumerate(lines, 1):
    if "@app.get(\"/files/" in line or "@app.get('/files/" in line or "def get_file(" in line or "def proxy_file(" in line or "/files/{file_id" in line:
        in_block = True
    if in_block:
        current_block.append(f"L{idx}: {line}")
        if line.startswith("def ") and len(current_block) > 1:
            in_block = False
            print("\n".join(current_block[:-1]))
            current_block = [f"L{idx}: {line}"]
        elif line.strip() == "" and len(current_block) > 30:
            in_block = False
            print("\n".join(current_block))
            current_block = []

if current_block:
    print("\n".join(current_block))


print("\n=== AUDITING R2: format_header imports & definitions ===")
format_header_usages = []
for dirpath, _, filenames in os.walk(root_dir):
    if ".git" in dirpath or "__pycache__" in dirpath or ".agents" in dirpath or "venv" in dirpath:
        continue
    for fname in filenames:
        if fname.endswith(".py"):
            fpath = os.path.join(dirpath, fname)
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                flines = f.readlines()
            for idx, line in enumerate(flines, 1):
                if "format_header" in line:
                    format_header_usages.append((os.path.relpath(fpath, root_dir), idx, line.strip()))

print(f"Found {len(format_header_usages)} occurrences of format_header across the codebase.")
print("Checking key files: user_manager.py, main.py, post_helpers.py:")
for path, line_no, content in format_header_usages:
    if any(k in path for k in ["user_manager.py", "main.py", "post_helpers.py"]):
        print(f"  {path}:{line_no} -> {content}")


print("\n=== AUDITING R3: db_sleep & LazyLock in common/db_pool.py & common/database.py ===")
db_pool_path = os.path.join(root_dir, "common", "db_pool.py")
with open(db_pool_path, "r", encoding="utf-8") as f:
    db_pool_content = f.read()

print("common/db_pool.py - LazyLock & db_sleep:")
for idx, line in enumerate(db_pool_content.splitlines(), 1):
    if "class LazyLock" in line or "def acquire" in line or "def release" in line or "def db_sleep" in line or "is_owned_by_current_task" in line or "locked_by_current_task" in line or "_owner" in line:
        print(f"  L{idx}: {line}")

database_py_path = os.path.join(root_dir, "common", "database.py")
with open(database_py_path, "r", encoding="utf-8") as f:
    database_content = f.read()

asyncio_sleeps_in_db = [
    (idx, line.strip())
    for idx, line in enumerate(database_content.splitlines(), 1)
    if "asyncio.sleep" in line
]
print(f"\nRemaining asyncio.sleep calls in common/database.py: {len(asyncio_sleeps_in_db)}")
for line_no, content in asyncio_sleeps_in_db:
    print(f"  Line {line_no}: {content}")

