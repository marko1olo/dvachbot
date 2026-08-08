import ast

with open(r"C:\Users\danat\Desktop\dvachbot\common\database.py", 'r', encoding='utf-8') as f:
    tree = ast.parse(f.read(), filename="database.py")

class NameVisitor(ast.NodeVisitor):
    def __init__(self):
        self.defined = set()
        self.imported = set()
        self.used_as_func = set()

    def visit_Import(self, node):
        for alias in node.names:
            name = alias.asname or alias.name
            self.imported.add(name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        for alias in node.names:
            name = alias.asname or alias.name
            self.imported.add(name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        self.defined.add(node.name)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        self.defined.add(node.name)
        self.generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
            self.used_as_func.add((node.func.id, node.lineno))
        self.generic_visit(node)

visitor = NameVisitor()
visitor.visit(tree)

print("Is db_sleep imported?", 'db_sleep' in visitor.imported)
print("Is db_sleep defined?", 'db_sleep' in visitor.defined)

db_sleep_calls = [lineno for name, lineno in visitor.used_as_func if name == 'db_sleep']
print(f"db_sleep is called {len(db_sleep_calls)} times at lines: {db_sleep_calls[:10]}...")
