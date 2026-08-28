import subprocess
import traceback

def run_cmd(cmd):
    return subprocess.check_output(cmd, shell=False, stderr=subprocess.STDOUT).decode('utf-8').strip()

def main():
    try:
        log = run_cmd(["git", "branch"])
        print(log)
    except Exception:
        print(traceback.format_exc())

main()
