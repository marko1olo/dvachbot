import re
import ast

def find_regex_in_loop(filename):
    with open(filename, 'r') as f:
        source = f.read()

    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, (ast.For, ast.While)):
            for sub_node in ast.walk(node):
                if isinstance(sub_node, ast.Call):
                    if isinstance(sub_node.func, ast.Attribute):
                        if isinstance(sub_node.func.value, ast.Name) and sub_node.func.value.id == 're' and sub_node.func.attr == 'compile':
                            print(f"Found re.compile inside loop at line {sub_node.lineno}")

find_regex_in_loop("ukrainian_mode.py")
