import re

with open('site_tgach/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace `name="error.jinja2", {` with `name="error.jinja2", context={`
content = re.sub(r'(name=\"[^\"]+\.jinja2\")\s*,\s*\{', r'\1, context={', content)

with open('site_tgach/main.py', 'w', encoding='utf-8') as f:
    f.write(content)
