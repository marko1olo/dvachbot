import re

with open("pr_merger.py", "r", encoding="utf-8") as f:
    content = f.read()

new_content = content.replace(
    "return subprocess.check_output(cmd, shell=False, stderr=subprocess.STDOUT, timeout=10).decode('utf-8').strip()",
    "return subprocess.check_output(cmd, shell=False, stderr=subprocess.STDOUT, timeout=60).decode('utf-8').strip()"
)

with open("pr_merger.py", "w", encoding="utf-8") as f:
    f.write(new_content)
