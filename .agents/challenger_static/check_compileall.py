import compileall
import os
import sys

workspace = r"C:\Users\danat\Desktop\dvachbot"
os.chdir(workspace)

print("Running compileall.compile_dir('.', maxlevels=5, quiet=0)...")
res = compileall.compile_dir('.', maxlevels=5, quiet=0, force=False)
print("compile_dir returned:", res)
