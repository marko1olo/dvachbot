import os

project_root = r"C:\Users\danat\Desktop\dvachbot"

for root, dirs, files in os.walk(project_root):
    if ".agents" in root or "__pycache__" in root or ".git" in root:
        continue
    for file in files:
        if file.endswith(".py"):
            path = os.path.join(root, file)
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            if "postcopies_daily_cleanup_loop" in content:
                print(f"Found in: {os.path.relpath(path, project_root)}")
