import ast
import os

py_files = []
for root, dirs, files in os.walk('.'):
    if '.venv' in root or 'venv' in root or '.git' in root or 'scratch' in root:
        continue
    for f in files:
        if f.endswith('.py'):
            py_files.append(os.path.join(root, f))

print(f"Analyzing {len(py_files)} python files...")

time_sleep_in_async = []
sqlite_in_async = []

for pf in py_files:
    try:
        with open(pf, 'r', encoding='utf-8', errors='ignore') as f:
            code = f.read()
        tree = ast.parse(code, filename=pf)
    except Exception as e:
        continue

    class Visitor(ast.NodeVisitor):
        def __init__(self, filename):
            self.filename = filename
            self.current_async_func = None

        def visit_AsyncFunctionDef(self, node):
            old_func = self.current_async_func
            self.current_async_func = node.name
            self.generic_visit(node)
            self.current_async_func = old_func

        def visit_Call(self, node):
            if self.current_async_func:
                # check for time.sleep
                if isinstance(node.func, ast.Attribute):
                    if isinstance(node.func.value, ast.Name) and node.func.value.id == 'time' and node.func.attr == 'sleep':
                        time_sleep_in_async.append((self.filename, node.lineno, self.current_async_func))
                    elif node.func.attr in ('execute', 'executemany', 'fetchall', 'fetchone', 'commit'):
                        # check if it's sync sqlite execution
                        sqlite_in_async.append((self.filename, node.lineno, self.current_async_func, node.func.attr))
                elif isinstance(node.func, ast.Name):
                    if node.func.id == 'sleep':
                        # could be time.sleep imported as sleep
                        pass
            self.generic_visit(node)

    v = Visitor(pf)
    v.visit(tree)

print("\n--- time.sleep in async functions ---")
for item in time_sleep_in_async[:30]:
    print(f"{item[0]}:{item[1]} in {item[2]}")

print(f"\nTotal DB/sync calls in async funcs: {len(sqlite_in_async)}")
