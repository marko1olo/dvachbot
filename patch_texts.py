import re

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = re.sub(r'message\.text\.split\(\)', r'(message.text or message.caption or \"\").split()', content)
content = re.sub(r'message\.text\.lstrip\(', r'(message.text or message.caption or \"\").lstrip(', content)
content = re.sub(r'_parse_summarize_args\(message\.text\)', r'_parse_summarize_args(message.text or message.caption or \"\")', content)

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Patch applied')
