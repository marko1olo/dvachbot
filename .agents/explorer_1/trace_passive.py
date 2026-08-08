import glob
import re

print("=== SEARCHING FOR PASSIVE SLICE & RELATED PHRASES ===")
files = glob.glob("**/*.py", recursive=True)
for fname in files:
    if "venv" in fname or ".mypy_cache" in fname or ".pytest_cache" in fname:
        continue
    try:
        with open(fname, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            for idx, line in enumerate(lines):
                if any(k in line for k in ["passive_slice", "passive_media_slice_size", "delivery_phase", "passive_recipients"]):
                    print(f"{fname}:{idx+1}: {line.strip()}")
    except Exception as e:
        pass
