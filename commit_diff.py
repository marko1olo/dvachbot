import subprocess
out = subprocess.check_output("git diff origin/main main.py", shell=True, text=True)
print(out[:1000])
