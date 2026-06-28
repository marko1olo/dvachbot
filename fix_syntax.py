with open("Dubsite_tgach/main.py", "r") as f:
    lines = f.readlines()
for i, line in enumerate(lines):
    if "❌ Какая-то хуйня с данными., \"type\": \"text\"" in line:
        lines[i] = line.replace("❌ Какая-то хуйня с данными.,", "❌ Какая-то хуйня с данными.\",")

with open("Dubsite_tgach/main.py", "w") as f:
    f.writelines(lines)
