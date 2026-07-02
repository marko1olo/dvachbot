import re

with open('main.py', 'r') as f:
    content = f.read()

# Very basic manual resolution just to keep our changes, though usually doing `git checkout HEAD main.py` or `git reset` handles it if we hadn't already got stuck.
# Since the git status indicated we have merge conflict markers in main.py, let's just resolve it by keeping OUR side (which has the performance fix).
# If there are no markers, we just exit.

if '<<<<<<<' in content:
    # This is a very naive regex but since we're stuck in a loop we just want to force a clean file.
    # It tries to find a merge conflict block and keep the top part (HEAD)
    resolved_content = re.sub(r'<<<<<<< HEAD\n(.*?)=======\n.*?>>>>>>> [a-zA-Z0-9_\-]+\n', r'\1', content, flags=re.DOTALL)
    with open('main.py', 'w') as f:
        f.write(resolved_content)
    print("Resolved merge conflict markers.")
else:
    print("No merge conflict markers found.")
