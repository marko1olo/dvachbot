import unittest
import sys
import os

project_root = r"C:\Users\danat\Desktop\dvachbot"
sys.path.insert(0, project_root)

test_file = os.path.join(project_root, "tests", "test_db_pool.py")
if os.path.exists(test_file):
    loader = unittest.TestLoader()
    suite = loader.discover(os.path.join(project_root, "tests"), pattern="test_db_pool.py")
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)
