#!/bin/bash
git checkout origin/main -- pyproject.toml
cat << 'INNER_EOF' >> pyproject.toml

[tool.pytest.ini_options]
pythonpath = "."
INNER_EOF
git add pyproject.toml
git commit -m "Resolve merge conflict in pyproject.toml"
