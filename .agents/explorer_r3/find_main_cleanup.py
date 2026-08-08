with open(r"C:\Users\danat\Desktop\dvachbot\main.py", "r", encoding="utf-8") as f:
    for idx, line in enumerate(f, 1):
        if "postcopies_daily_cleanup_loop" in line:
            print(f"Line {idx}: {line.strip()}")
