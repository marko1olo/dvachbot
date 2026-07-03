import ast
import json
import os

def extract_strings_from_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return []
    
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []

    phrases = []
    target_methods = {
        'send_message', 'reply', 'answer', 'edit_text', 
        'answer_callback_query', 'send_photo', 'send_document', 
        'reply_text', 'reply_photo'
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = None
            if isinstance(node.func, ast.Attribute):
                func_name = node.func.attr
            elif isinstance(node.func, ast.Name):
                func_name = node.func.id
                
            if func_name in target_methods:
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        # Filter only Cyrillic strings
                        if any('\u0400' <= c <= '\u04FF' for c in arg.value):
                            phrases.append({'file': filepath, 'line': node.lineno, 'text': arg.value})
                for kw in node.keywords:
                    if kw.arg == 'text' and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        if any('\u0400' <= c <= '\u04FF' for c in kw.value.value):
                            phrases.append({'file': filepath, 'line': node.lineno, 'text': kw.value.value})
    return phrases

all_phrases = []
for root, dirs, files in os.walk('.'):
    # skip venv, git, etc
    if 'venv' in root or '.git' in root or '__pycache__' in root:
        continue
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            all_phrases.extend(extract_strings_from_file(filepath))

# Remove duplicates based on text
unique_phrases = {}
for p in all_phrases:
    if p['text'] not in unique_phrases:
        unique_phrases[p['text']] = []
    unique_phrases[p['text']].append(f"{p['file']}:{p['line']}")

# Format output
output = []
for text, locs in unique_phrases.items():
    output.append({'text': text, 'locations': locs})

with open('phrases_all.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"Extracted {len(output)} unique phrases to phrases_all.json")
