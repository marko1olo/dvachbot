import sys
import unittest
from pathlib import Path

# Adding project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Mock admin config before importing permissions
import site_tgach.admin_config
site_tgach.admin_config.ADMIN_IDS = {9999}

# Also need to make sure python can resolve `permissions` from Dubsite_tgach
sys.path.insert(0, str(PROJECT_ROOT / "Dubsite_tgach"))
from permissions import check_perm

class TestCheckPerm(unittest.TestCase):
    def test_empty_user(self):
        self.assertFalse(check_perm({}, 'user'))
        self.assertFalse(check_perm(None, 'user'))

    def test_admin_id(self):
        admin_id = 9999
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
