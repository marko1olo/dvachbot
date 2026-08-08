import unittest
import sys
import os

project_root = r"C:\Users\danat\Desktop\dvachbot"
sys.path.insert(0, project_root)

# Let's run test_db_pool.py if it exists
test_file = os.path.join(project_root, "tests", "test_db_pool.py")
if os.path.exists(test_file):
    print("Running test_db_pool.py...")
    os.system(f"{sys.executable} -m pytest {test_file}")
else:
    print("test_db_pool.py not found.")
