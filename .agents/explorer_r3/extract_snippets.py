import re

with open(r"C:\Users\danat\Desktop\dvachbot\common\database.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

context_snippets = []

for idx, line in enumerate(lines, 1):
    if "db_sleep" in line:
        start = max(1, idx - 12)
        end = min(len(lines), idx + 5)
        snippet = "".join([f"{i:4d}: {lines[i-1]}" for i in range(start, end+1)])
        context_snippets.append((idx, snippet))

print(f"Total db_sleep contexts: {len(context_snippets)}")

# Print sample 10 snippets
with open(r"C:\Users\danat\Desktop\dvachbot\.agents\explorer_r3\db_sleep_snippets.txt", "w", encoding="utf-8") as out:
    for idx, snippet in context_snippets:
        out.write(f"=== LINE {idx} ===\n")
        out.write(snippet + "\n\n")

print("Snippets written to db_sleep_snippets.txt")
