# Is there another loop?
import ast
from pprint import pprint

tree = ast.parse(open('ukrainian_mode.py').read())
for node in ast.walk(tree):
    if isinstance(node, (ast.For, ast.While, ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp)):
        for sub_node in ast.walk(node):
            if isinstance(sub_node, ast.Attribute) and sub_node.attr == 'compile':
                print(f"Loop containing re.compile at line {node.lineno}")
