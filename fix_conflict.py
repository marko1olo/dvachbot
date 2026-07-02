import subprocess

def fix_conflict():
    # The tests were rewritten or added initially, and it seems there's a conflict
    # because they exist on both main and our branch. Since our branch has the updated
    # comprehensive tests for ghost worker, we want to resolve the conflict by picking ours

    # Just checkout our branch's tests entirely
    subprocess.run(["git", "checkout", "origin/main", "--", "tests/test_witching_hour.py"], check=True)
    subprocess.run(["git", "commit", "-m", "Merge origin/main into testing-witching-hour-worker"], check=False)

fix_conflict()
