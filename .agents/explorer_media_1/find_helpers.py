import sys

sys.stdout.reconfigure(encoding='utf-8')

filepath = r"C:\Users\danat\Desktop\dvachbot\site_tgach\main.py"

with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

print("Search for get_cached_file_path and get_file_mirrors in main.py and imported modules:")
for idx, line in enumerate(lines, 1):
    if any(k in line for k in ["def get_cached_file_path", "def get_file_mirrors", "import get_cached_file_path", "import get_file_mirrors"]):
        print(f"Line {idx:5d}: {line.strip()}")

