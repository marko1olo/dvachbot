import unittest
import ast
import os

class TestNotificationFallback(unittest.TestCase):
    def test_effective_thread_id_fallback(self):
        """
        Verify that effective_thread_id correctly falls back to source_post_num
        if thread_id is missing when recording a notification.
        """
        filepath = os.path.join(os.path.dirname(__file__), '..', 'common', 'database.py')
        with open(filepath, 'r') as f:
            tree = ast.parse(f.read())

        found_assignment = False

        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == 'add_reply_to_notification_queue':
                for stmt in ast.walk(node):
                    if isinstance(stmt, ast.Assign):
                        for target in stmt.targets:
                            if isinstance(target, ast.Name) and target.id == 'effective_thread_id':
                                # Verify the assignment is an IfExp
                                self.assertIsInstance(stmt.value, ast.IfExp)

                                # Check the condition (test)
                                self.assertIsInstance(stmt.value.test, ast.Name)
                                self.assertEqual(stmt.value.test.id, 'thread_id')

                                # Check the true branch (body)
                                self.assertIsInstance(stmt.value.body, ast.Call)
                                self.assertEqual(stmt.value.body.func.id, 'str')
                                self.assertEqual(stmt.value.body.args[0].id, 'thread_id')

                                # Check the false branch (orelse)
                                self.assertIsInstance(stmt.value.orelse, ast.Call)
                                self.assertEqual(stmt.value.orelse.func.id, 'str')
                                self.assertEqual(stmt.value.orelse.args[0].id, 'source_post_num')

                                found_assignment = True

        self.assertTrue(found_assignment, "effective_thread_id assignment with fallback not found")

if __name__ == '__main__':
    unittest.main()
