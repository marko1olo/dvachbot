import os

def search_repo(root_dir):
    for root, dirs, files in os.walk(root_dir):
        if '.git' in root or '__pycache__' in root or '.venv' in root:
            continue
        for f in files:
            if f.endswith('.py'):
                path = os.path.join(root, f)
                with open(path, 'r', encoding='utf-8', errors='ignore') as file:
                    content = file.read()
                    if 'db_sleep' in content:
                        print(f"db_sleep found in: {path}")

search_repo(r"C:\Users\danat\Desktop\dvachbot")
