import ast
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('main.py', encoding='utf-8') as f:
    lines = f.readlines()

tree = ast.parse("".join(lines))

target_funcs = {
    '_build_archive_header',
    '_format_archive_text_content',
    '_site_file_send_type',
    '_send_archive_media_group',
    '_send_archive_single_media',
    '_send_archive_media',
    '_update_archive_post_content',
    'post_archive_to_channel',
    '_sync_generate_thread_archive',
    'archive_thread'
}

extract_blocks = []
remove_lines = set()

for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if node.name in target_funcs:
            # We want to extract decorators as well
            if hasattr(node, 'decorator_list') and getattr(node, 'decorator_list', None):
                start = node.decorator_list[0].lineno - 1
            else:
                start = node.lineno - 1
            end = node.end_lineno
            block = "".join(lines[start:end])
            extract_blocks.append(block)
            for i in range(start, end):
                remove_lines.add(i)

new_main_lines = [l for i, l in enumerate(lines) if i not in remove_lines]

with open('main.py', 'w', encoding='utf-8') as f:
    f.write("".join(new_main_lines))

with open('archive_manager.py', 'w', encoding='utf-8') as f:
    f.write("import asyncio\n")
    f.write("from shared_state import *\n")
    f.write("from typing import *\n")
    f.write("\n\n")
    f.write("\n".join(extract_blocks))

print(f"Extracted {len(extract_blocks)} functions to archive_manager.py")
