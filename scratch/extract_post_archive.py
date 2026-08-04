import ast
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('post_processor.py', encoding='utf-8') as f:
    lines = f.readlines()

tree = ast.parse("".join(lines))

target_funcs = {
    'post_special_num_to_channel',
    'post_to_archive_channel'
}

extract_blocks = []
remove_lines = set()

for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if node.name in target_funcs:
            start = node.lineno - 1
            end = node.end_lineno
            block = "".join(lines[start:end])
            extract_blocks.append(block)
            for i in range(start, end):
                remove_lines.add(i)

new_post_lines = [l for i, l in enumerate(lines) if i not in remove_lines]

with open('post_processor.py', 'w', encoding='utf-8') as f:
    f.write("".join(new_post_lines))

with open('archive_manager.py', 'a', encoding='utf-8') as f:
    f.write("\n\n")
    f.write("\n".join(extract_blocks))

print(f"Extracted {len(extract_blocks)} functions to archive_manager.py")
