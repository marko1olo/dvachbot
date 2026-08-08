import os
import sys
import subprocess

os.environ["PYTHONPATH"] = r"C:\Users\danat\Desktop\dvachbot"
os.environ["PYTHONUNBUFFERED"] = "1"

cmd = [
    r"C:\Users\danat\Desktop\dvachbot\venv\Scripts\python.exe",
    "-m", "pytest",
    r"C:\Users\danat\Desktop\dvachbot\tests\test_db_pool.py",
    r"C:\Users\danat\Desktop\dvachbot\tests\test_database_sync.py",
    r"C:\Users\danat\Desktop\dvachbot\tests\test_database.py",
    r"C:\Users\danat\Desktop\dvachbot\tests\test_dbchecker.py",
    "-v"
]

res = subprocess.run(cmd, capture_output=True, text=True)
print("STDOUT:")
print(res.stdout)
print("STDERR:")
print(res.stderr)
print("EXIT CODE:", res.returncode)
