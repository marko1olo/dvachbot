#!/bin/bash
git config --global user.email "you@example.com"
git config --global user.name "Your Name"
git merge origin/main --no-edit
if [ $? -ne 0 ]; then
  git checkout --ours pyproject.toml
  git add pyproject.toml
  git commit -m "Resolve merge conflict in pyproject.toml"
fi
