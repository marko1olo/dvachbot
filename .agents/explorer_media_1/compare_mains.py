import sys

sys.stdout.reconfigure(encoding='utf-8')

for fpath in [r"C:\Users\danat\Desktop\dvachbot\main.py", r"C:\Users\danat\Desktop\dvachbot\site_tgach\main.py"]:
    print(f"=== FIRST 30 LINES OF {fpath} ===")
    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
        for idx, line in enumerate(lines[:30], 1):
            print(f"{idx:3d}: {line.rstrip()}")

