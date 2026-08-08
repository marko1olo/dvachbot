with open('common/database.py', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

out = []
for i in range(7800, min(len(lines), 7850)):
    out.append(f"{i+1}: {lines[i].rstrip()}")

with open('scratch/db_7800.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))
print("Wrote scratch/db_7800.txt")
