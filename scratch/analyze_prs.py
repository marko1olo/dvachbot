import subprocess
import json

result = subprocess.run(['git', 'branch', '-r', '--no-merged', 'origin/main'], capture_output=True, text=True, encoding='utf-8', errors='replace')
branches = [b.strip() for b in result.stdout.split('\n') if b.strip() and '->' not in b]

pr_data = []

for b in branches:
    log = subprocess.run(['git', 'log', '-1', '--oneline', b], capture_output=True, text=True, encoding='utf-8', errors='replace').stdout.strip()
    diff_stat = subprocess.run(['git', 'diff', '--stat', f"origin/main..{b}"], capture_output=True, text=True, encoding='utf-8', errors='replace').stdout.strip()
    diff = subprocess.run(['git', 'diff', f"origin/main..{b}"], capture_output=True, text=True, encoding='utf-8', errors='replace').stdout.strip()
    
    pr_data.append({
        "branch": b,
        "commit": log,
        "stat": diff_stat,
        "diff_len": len(diff),
        "diff": diff[:3000] if len(diff) > 3000 else diff
    })

with open('scratch/pr_analysis.json', 'w', encoding='utf-8') as f:
    json.dump(pr_data, f, indent=2, ensure_ascii=False)

print(f"Dumped {len(pr_data)} branches to scratch/pr_analysis.json")
