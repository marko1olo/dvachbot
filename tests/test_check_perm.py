import sys
import os
import unittest

# Setup required env var
os.environ["SECRET_KEY"] = "test-secret-key-12345"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    import asyncio
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    import Dubsite_tgach.main
    Dubsite_tgach.main.ADMIN_IDS = [12345, 67890]
    from Dubsite_tgach.main import check_perm
except ImportError as e:
    print(f"ImportError: {e}")
    sys.exit(1)

class TestCheckPerm(unittest.TestCase):
    def test_empty_user(self):
        self.assertFalse(check_perm({}, 'user'))
        self.assertFalse(check_perm(None, 'user'))

    def test_admin_id(self):
        # Even with no role, an admin ID should always return True
        self.assertTrue(check_perm({'id': 12345}, 'admin'))
        self.assertTrue(check_perm({'id': 67890}, 'admin'))

    def test_role_hierarchy_admin(self):
        user = {'id': 1, 'role': 'admin'}
        self.assertTrue(check_perm(user, 'user'))
        self.assertTrue(check_perm(user, 'janitor'))
        self.assertTrue(check_perm(user, 'mod'))
        self.assertTrue(check_perm(user, 'admin'))

    def test_role_hierarchy_mod(self):
        user = {'id': 1, 'role': 'mod'}
        self.assertTrue(check_perm(user, 'user'))
        self.assertTrue(check_perm(user, 'janitor'))
        self.assertTrue(check_perm(user, 'mod'))
        self.assertFalse(check_perm(user, 'admin'))

    def test_role_hierarchy_janitor(self):
        user = {'id': 1, 'role': 'janitor'}
        self.assertTrue(check_perm(user, 'user'))
        self.assertTrue(check_perm(user, 'janitor'))
        self.assertFalse(check_perm(user, 'mod'))
        self.assertFalse(check_perm(user, 'admin'))

    def test_role_hierarchy_user(self):
        user = {'id': 1, 'role': 'user'}
        self.assertTrue(check_perm(user, 'user'))
        self.assertFalse(check_perm(user, 'janitor'))
        self.assertFalse(check_perm(user, 'mod'))
        self.assertFalse(check_perm(user, 'admin'))

    def test_default_role(self):
        # A user dict with an ID but no role defaults to 'user'
        user = {'id': 1}
        self.assertTrue(check_perm(user, 'user'))
        self.assertFalse(check_perm(user, 'janitor'))

    def test_invalid_role(self):
        # If the user has an invalid role, it defaults to level 0 (like user)
        user = {'id': 1, 'role': 'non_existent_role'}
        self.assertTrue(check_perm(user, 'user'))
        self.assertFalse(check_perm(user, 'janitor'))

        # Checking against an invalid role should require level >= 0
        user_mod = {'id': 1, 'role': 'mod'}
        self.assertTrue(check_perm(user_mod, 'non_existent_role'))

if __name__ == "__main__":
    unittest.main()
