import re

with open("pr_merger.py", "r") as f:
    content = f.read()

# Replace timeout implementation with simple timeout on communicate/run
new_content = re.sub(
    r"def run_cmd\(cmd\):\n.*?return subprocess\.check_output\(cmd, shell=False, stderr=subprocess\.STDOUT\)\.decode\('utf-8'\)\.strip\(\)",
    """def run_cmd(cmd):
    return subprocess.check_output(cmd, shell=False, stderr=subprocess.STDOUT, timeout=60).decode('utf-8').strip()""",
    content, flags=re.DOTALL
)

with open("pr_merger.py", "w") as f:
    f.write(new_content)
