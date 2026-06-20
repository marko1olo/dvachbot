import ast
import unittest
from pathlib import Path

class TestFallbackThreadID(unittest.TestCase):
    def test_fallback_thread_id_ast(self):
        db_file = Path("common/database.py")
        self.assertTrue(db_file.exists(), "common/database.py not found")

        with open(db_file, "r", encoding="utf-8") as f:
            code = f.read()

        tree = ast.parse(code)

        found = False

        class IfExpVisitor(ast.NodeVisitor):
            def visit_IfExp(self, node):
                # We are looking for: str(t_id) if t_id else str(rep_num)
                # test: Name(id='t_id')
                # body: Call(func=Name(id='str'), args=[Name(id='t_id')])
                # orelse: Call(func=Name(id='str'), args=[Name(id='rep_num')])

                try:
                    is_test_match = isinstance(node.test, ast.Name) and node.test.id == 't_id'

                    is_body_match = (
                        isinstance(node.body, ast.Call) and
                        isinstance(node.body.func, ast.Name) and node.body.func.id == 'str' and
                        len(node.body.args) == 1 and isinstance(node.body.args[0], ast.Name) and
                        node.body.args[0].id == 't_id'
                    )

                    is_orelse_match = (
                        isinstance(node.orelse, ast.Call) and
                        isinstance(node.orelse.func, ast.Name) and node.orelse.func.id == 'str' and
                        len(node.orelse.args) == 1 and isinstance(node.orelse.args[0], ast.Name) and
                        node.orelse.args[0].id == 'rep_num'
                    )

                    if is_test_match and is_body_match and is_orelse_match:
                        nonlocal found
                        found = True
                except AttributeError:
                    pass

                self.generic_visit(node)

        IfExpVisitor().visit(tree)
        self.assertTrue(found, "The fallback thread ID logic 'str(t_id) if t_id else str(rep_num)' was not found in common/database.py")

if __name__ == '__main__':
    unittest.main()
