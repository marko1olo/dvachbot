import subprocess
import re

# Get all remote branches
output = subprocess.check_output(['git', 'branch', '-r']).decode('utf-8')
branches = [b.strip() for b in output.split('\n') if b.strip() and '->' not in b and 'origin/main' not in b]

prs = []
for branch in branches:
    # Skip pr/X branches as they might just be duplicate refs
    if branch.startswith('origin/pr/'):
        continue
        
    try:
        # Check if it has commits not in main
        log = subprocess.check_output(['git', 'log', f'main..{branch}', '--oneline']).decode('utf-8').strip()
        if not log:
            continue
            
        commits = log.split('\n')
        # Get diff stat
        diffstat = subprocess.check_output(['git', 'diff', '--shortstat', f'main...{branch}']).decode('utf-8').strip()
        
        prs.append({
            'branch': branch,
            'commits': commits,
            'diffstat': diffstat
        })
    except subprocess.CalledProcessError:
        pass

# Group and print
prs.sort(key=lambda x: x['branch'])
with open('prs_analysis.txt', 'w', encoding='utf-8') as f:
    f.write(f"Found {len(prs)} active branches with diffs against main:\\n")
    for pr in prs:
        f.write(f"Branch: {pr['branch']}\\n")
        f.write(f"Diff: {pr['diffstat']}\\n")
        f.write(f"Commits: {len(pr['commits'])} (Latest: {pr['commits'][0]})\\n")
        f.write("-" * 40 + "\\n")
print("Done. Saved to prs_analysis.txt")
