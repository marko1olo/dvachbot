with open('common/database.py', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

out = []
for idx, line in enumerate(lines):
    if 'def get_post_copies' in line:
        for i in range(max(0, idx-5), min(len(lines), idx+45)):
            out.append(f"{i+1}: {lines[i].rstrip()}")

with open('scratch/get_post_copies.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))
print("Wrote scratch/get_post_copies.txt")
