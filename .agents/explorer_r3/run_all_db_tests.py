import unittest
import sys
import os

project_root = r"C:\Users\danat\Desktop\dvachbot"
sys.path.insert(0, project_root)

db_test_files = [
    "test_db_pool.py",
    "test_database_sync.py",
    "test_adversarial_m3.py",
    "test_challenger_m3_stress.py"
]

for tf in db_test_files:
    full_path = os.path.join(project_root, "tests", tf)
    if os.path.exists(full_path):
        print(f"\n=================== RUNNING {tf} ===================")
        suite = unittest.TestLoader().loadTestsFromName(f"tests.{tf[:-3]}")
        runner = unittest.TextTestRunner(verbosity=1)
        runner.run(suite)
