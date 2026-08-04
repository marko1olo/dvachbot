import ast
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('main.py', encoding='utf-8') as f:
    lines = f.readlines()

tree = ast.parse("".join(lines))

target_names = {
    'MIRROR_CHANNELS', 'ARCHIVE_CHANNEL_ID', 'ARCHIVE_POSTING_BOT_ID',
    'AUTHORIZED_ARCHIVE_BOTS', 'SPECIAL_NUMERALS_CONFIG'
}

extract_blocks = []
remove_lines = set()

for node in tree.body:
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if getattr(target, 'id', None) in target_names:
                start = node.lineno - 1
                end = node.end_lineno
                block = "".join(lines[start:end])
                extract_blocks.append(block)
                for i in range(start, end):
                    remove_lines.add(i)

new_main_lines = [l for i, l in enumerate(lines) if i not in remove_lines]

with open('main.py', 'w', encoding='utf-8') as f:
    f.write("".join(new_main_lines))

with open('shared_state.py', 'a', encoding='utf-8') as f:
    f.write("\n\n# --- Archive Config ---\n")
    f.write("\n".join(extract_blocks))
    f.write("\n")

print(f"Extracted {len(extract_blocks)} configs from main.py to shared_state.py")
