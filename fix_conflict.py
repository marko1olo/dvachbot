with open("pyproject.toml", "r") as f:
    lines = f.readlines()

new_lines = []
skip = False
for line in lines:
    if line.startswith("<<<<<<<"):
        skip = True
        new_lines.append("[tool.pytest.ini_options]\npythonpath = [\n  \".\",\n  \"verification_scripts\"\n]\n")
    elif line.startswith("======="):
        pass
    elif line.startswith(">>>>>>>"):
        skip = False
    elif not skip:
        new_lines.append(line)

with open("pyproject.toml", "w") as f:
    f.writelines(new_lines)
