import subprocess

def run_cmd(cmd, check=True):
    try:
        # Note: shell=True removed to prevent command injection
        return subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode('utf-8').strip()
    except subprocess.CalledProcessError as e:
        if check:
            raise
        return e.output.decode('utf-8').strip()

def main():
    print("Starting Automated PR Triage...")
    
    # 1. Skip fetch
    # run_cmd(["git", "fetch", "--all"])
    
    # 2. List remote branches
    output = run_cmd(["git", "--no-pager", "branch", "-r"])
    branches = [b.strip() for b in output.split('\n') if b.strip() and '->' not in b and 'origin/main' not in b]
    
    # 3. Filter branches
    valid_branches = []
    for branch in branches:
        if branch.startswith('origin/pr/'):
            continue
            
        try:
            log = run_cmd(["git", "--no-pager", "log", f"main..{branch}", "--oneline"])
            if not log:
                continue # No commits to merge
            
            diffstat = run_cmd(["git", "--no-pager", "diff", "--shortstat", f"main...{branch}"])
            if not diffstat.strip():
                continue # Empty diff, already merged or empty
                
            valid_branches.append(branch)
        except Exception:
            pass

    print(f"Found {len(valid_branches)} valid branches to attempt merging.")
    
    success = []
    failed = []
    
    # 4. Sorting logic based on naming (Security > Test > Chore/Cleanup)
    def priority(b):
        b_lower = b.lower()
        if 'sql' in b_lower or 'perf' in b_lower or 'optimize' in b_lower: return 0
        if 'fix' in b_lower or 'test' in b_lower: return 1
        return 2
        
    valid_branches.sort(key=priority)
    
    # 5. Attempt merges
    for branch in valid_branches:
        print(f"Attempting merge for: {branch} ...")
        
        # Start merge
        merge_cmd = ["git", "merge", "--no-edit", "-m", f"Merge {branch}", branch]
        try:
            res = run_cmd(merge_cmd, check=False)
            
            if "Merge conflict" in res or "CONFLICT" in res:
                print(f"  [CONFLICT] Aborting...")
                run_cmd(["git", "merge", "--abort"], check=False)
                failed.append((branch, "Conflict"))
            elif "Already up to date" in res:
                print(f"  [ALREADY MERGED]")
            else:
                print(f"  [SUCCESS]")
                success.append(branch)
                
        except Exception as e:
            print(f"  [FAILED] with exception. Aborting...")
            run_cmd(["git", "merge", "--abort"], check=False)
            failed.append((branch, "Error"))

    # Summary
    with open("merge_summary.txt", "w", encoding='utf-8') as f:
        f.write(f"Successfully merged: {len(success)}\n")
        for b in success:
            f.write(f"  - {b}\n")
            
        f.write(f"\nFailed/Conflicts: {len(failed)}\n")
        for b, reason in failed:
            f.write(f"  - {b} ({reason})\n")
            
    print("Done! See merge_summary.txt for details.")

if __name__ == '__main__':
    main()
