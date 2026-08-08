import re
from pathlib import Path

p = Path(r"C:\Users\danat\Desktop\dvachbot\site_tgach\templates\thread.jinja2")
content = p.read_text(encoding='utf-8')

for tag in ['body', 'html', 'main', 'header', 'footer']:
    matches_start = [(m.start(), content.count('\n', 0, m.start())+1) for m in re.finditer(rf'<{tag}\b', content)]
    matches_end = [(m.start(), content.count('\n', 0, m.start())+1) for m in re.finditer(rf'</{tag}>', content)]
    print(f"<{tag}> starts: {matches_start}, ends: {matches_end}")
