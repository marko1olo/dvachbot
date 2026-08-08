import sys
import os

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

sys.path.insert(0, r"C:\Users\danat\Desktop\dvachbot")

print("Starting main.py dry-run import check...")
try:
    import main
    print("✅ SUCCESS: main.py imported without errors.")
except Exception as e:
    print(f"❌ ERROR importing main.py: {e}")
    sys.exit(1)
