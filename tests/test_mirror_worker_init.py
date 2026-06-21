import unittest
import ast
import os

class TestMirrorWorkerInit(unittest.TestCase):
    def test_file_info_initialization(self):
        """
        Verify that file_info is initialized to None before the try block
        in the _process_single_task function of site_tgach/mirror_worker.py
        to prevent UnboundLocalError during HTTP fallback.
        """
        file_path = os.path.join(os.path.dirname(__file__), '..', 'site_tgach', 'mirror_worker.py')
        with open(file_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())

        found_function = False
        found_init = False

        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == '_process_single_task':
                found_function = True

                # Check for file_info = None assignment
                for child in ast.walk(node):
                    if isinstance(child, ast.Assign):
                        for target in child.targets:
                            if isinstance(target, ast.Name) and target.id == 'file_info':
                                # verify it's assigned to None
                                if isinstance(child.value, ast.Constant) and child.value.value is None:
                                    found_init = True
                                    break

        self.assertTrue(found_function, "Function _process_single_task not found in mirror_worker.py")
        self.assertTrue(found_init, "file_info = None initialization not found in _process_single_task")

if __name__ == '__main__':
    unittest.main()
