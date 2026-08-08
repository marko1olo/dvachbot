import ast

with open('delivery_manager.py', 'r', encoding='utf-8', errors='ignore') as f:
    code = f.read()

tree = ast.parse(code)

funcs = {}
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        funcs[node.name] = node

print("Functions in delivery_manager.py:")
for name in funcs:
    if 'durable' in name or 'passive' in name or 'delivered' in name:
        print(" -", name)
