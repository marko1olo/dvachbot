import sys

sys.stdout.reconfigure(encoding='utf-8')

filepath = r"C:\Users\danat\Desktop\dvachbot\main.py"

with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
    content = f.read()

print("Search in root main.py for web server / routes:")
for idx, line in enumerate(content.splitlines(), 1):
    if any(k in line.lower() for k in ["/file/", "/thumb/", "/i/", "/preview/", "web.Application", "fastapi", "@app."]):
        print(f"Line {idx:5d}: {line.strip()[:140]}")

