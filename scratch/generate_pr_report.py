import json

with open('scratch/pr_analysis.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

lines = ["# PR Analysis Report", ""]

for item in data:
    b = item['branch']
    if 'jules-' in b:
        continue
    c = item['commit']
    stat = item['stat'].split('\n')[-1] if item['stat'] else ""
    lines.append(f"## Branch: `{b}`")
    lines.append(f"**Commit:** {c}")
    lines.append(f"**Stat:** {stat}")
    lines.append("```diff")
    diff_snippet = "\n".join(item['diff'].split('\n')[:50]) # first 50 lines of diff
    lines.append(diff_snippet)
    lines.append("```")
    lines.append("")

with open('scratch/pr_report.md', 'w', encoding='utf-8') as f:
    f.write("\n".join(lines))
print("Wrote scratch/pr_report.md")
