import os
import sys

root_dir = r"C:\Users\danat\Desktop\dvachbot"

for root, dirs, files in os.walk(root_dir):
    if ".git" in root or ".venv" in root or "venv" in root or ".agents" in root:
        continue
    for file in files:
        if file.endswith(".py"):
            filepath = os.path.join(root, file)
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    if "initialize_database" in content:
                        print(f"Found 'initialize_database' in: {filepath}")
                    if "CREATE TABLE IF NOT EXISTS PostFiles" in content or "CREATE TABLE PostFiles" in content:
                        print(f"Found 'PostFiles table' in: {filepath}")
                    if "idx_postfiles_orig" in content:
                        print(f"Found 'idx_postfiles_orig' in: {filepath}")
            except Exception as e:
                pass
