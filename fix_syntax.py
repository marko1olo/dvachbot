with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('\\"\\"', '""')

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Fix applied.")
