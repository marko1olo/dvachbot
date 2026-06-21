import ast
import json

def extract_strings(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()
    
    tree = ast.parse(content)
    phrases = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr in ('send_message', 'reply', 'answer'):
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        phrases.append({'line': node.lineno, 'text': arg.value})
                for kw in node.keywords:
                    if kw.arg == 'text' and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        phrases.append({'line': node.lineno, 'text': kw.value.value})
            
    return phrases

phrases = extract_strings('main.py')
with open('phrases_main.json', 'w', encoding='utf-8') as f:
    json.dump(phrases, f, ensure_ascii=False, indent=2)

print(f"Extracted {len(phrases)} phrases to phrases_main.json")
