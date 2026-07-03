import subprocess
import traceback

def run_cmd(cmd):
    return subprocess.check_output(cmd, shell=False, stderr=subprocess.STDOUT).decode('utf-8').strip()

def main():
    try:
        branch = "optimize-notification-queue-deletion"
        log = run_cmd(["git", "branch"])
        print(log)
    except Exception as e:
        print(traceback.format_exc())

main()
