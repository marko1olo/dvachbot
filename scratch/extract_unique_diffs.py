import json

with open('scratch/pr_analysis.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Find the common "base diff" that appears in every branch - these are the noise
# The boilerplate: removing ujson try/except, except: instead of except Exception:, removing NICK_PREFIXES
BOILERPLATE_MARKERS = [
    "import ujson as json",
    "NICK_PREFIXES",
    "supervisor_keyboard_interrupt",
]

results = []

for item in data:
    b = item['branch']
    diff = item['diff']
    
    # Count how much of the diff is boilerplate
    boilerplate_hits = sum(1 for m in BOILERPLATE_MARKERS if m in diff)
    
    # Extract only the unique diffs (not in main.py or bot_watchdog.py, since those are all noise)
    unique_lines = []
    in_main_py = False
    in_watchdog = False
    in_unique_file = False
    
    for line in diff.split('\n'):
        if line.startswith('diff --git'):
            in_main_py = 'main.py' in line and 'site_tgach' not in line
            in_watchdog = 'bot_watchdog.py' in line
            in_unique_file = not in_main_py and not in_watchdog
        
        if in_unique_file and line.startswith(('+', '-')) and not line.startswith(('+++', '---')):
            unique_lines.append(f"[{b}] {line}")
    
    if unique_lines:
        results.append({
            "branch": b,
            "unique_changes": unique_lines
        })

with open('scratch/unique_changes.txt', 'w', encoding='utf-8') as f:
    for r in results:
        f.write(f"\n\n{'='*60}\n{r['branch']}\n{'='*60}\n")
        for line in r['unique_changes']:
            f.write(line + '\n')

print(f"Found {len(results)} branches with unique changes")
