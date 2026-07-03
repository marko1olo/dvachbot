import sys
import unittest
from pathlib import Path
import ast
import site_tgach.admin_config

# Adding project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

def load_check_perm():
    # Read the file Dubsite_tgach/main.py
    main_py_path = PROJECT_ROOT / "Dubsite_tgach" / "main.py"
    with open(main_py_path, 'r', encoding='utf-8') as f:
        source = f.read()

    # Parse to AST
    tree = ast.parse(source)

    # Extract exactly what we need for check_perm
    code_str = ""
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if getattr(target, 'id', '') == 'ROLE_HIERARCHY':
                    code_str += ast.unparse(node) + "\n"
        elif isinstance(node, ast.FunctionDef) and node.name == 'check_perm':
            code_str += ast.unparse(node) + "\n"

    # Setup the global variables that check_perm needs
    namespace = {
        'ADMIN_IDS': site_tgach.admin_config.ADMIN_IDS
    }

    # Execute the extracted AST code into our namespace
    exec(code_str, namespace)

    return namespace['check_perm']

check_perm = load_check_perm()

class TestCheckPerm(unittest.TestCase):
    def test_empty_user(self):
        self.assertFalse(check_perm({}, 'user'))
        self.assertFalse(check_perm(None, 'user'))

    def test_admin_id(self):
        # The admin IDs should be populated from site_tgach.admin_config.ADMIN_IDS
        admin_id = list(site_tgach.admin_config.ADMIN_IDS)[0]
        self.assertTrue(check_perm({'id': admin_id}, 'admin'))
        self.assertTrue(check_perm({'id': admin_id}, 'user'))
        self.assertTrue(check_perm({'id': admin_id}, 'janitor'))
        self.assertTrue(check_perm({'id': admin_id}, 'mod'))

    def test_regular_user(self):
        user = {'id': 1234, 'role': 'user'}
        self.assertTrue(check_perm(user, 'user'))
        self.assertFalse(check_perm(user, 'janitor'))
        self.assertFalse(check_perm(user, 'mod'))
        self.assertFalse(check_perm(user, 'admin'))

    def test_janitor(self):
        user = {'id': 1234, 'role': 'janitor'}
        self.assertTrue(check_perm(user, 'user'))
        self.assertTrue(check_perm(user, 'janitor'))
        self.assertFalse(check_perm(user, 'mod'))
        self.assertFalse(check_perm(user, 'admin'))

    def test_mod(self):
        user = {'id': 1234, 'role': 'mod'}
        self.assertTrue(check_perm(user, 'user'))
        self.assertTrue(check_perm(user, 'janitor'))
        self.assertTrue(check_perm(user, 'mod'))
        self.assertFalse(check_perm(user, 'admin'))

    def test_admin_role(self):
        user = {'id': 1234, 'role': 'admin'}
        self.assertTrue(check_perm(user, 'user'))
        self.assertTrue(check_perm(user, 'janitor'))
        self.assertTrue(check_perm(user, 'mod'))
        self.assertTrue(check_perm(user, 'admin'))

    def test_unknown_role(self):
        user = {'id': 1234, 'role': 'hacker'}
        self.assertTrue(check_perm(user, 'user'))
        self.assertFalse(check_perm(user, 'janitor'))

if __name__ == '__main__':
    unittest.main()
