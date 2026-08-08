import html.parser
import re
from pathlib import Path

class BodyTracer(html.parser.HTMLParser):
    def handle_starttag(self, tag, attrs):
        if tag in ('body', 'html', 'main', 'header', 'footer', 'div'):
            print(f"START <{tag}> at line {self.getpos()[0]}")
    def handle_endtag(self, tag):
        if tag in ('body', 'html', 'main', 'header', 'footer', 'div'):
            print(f"END </{tag}> at line {self.getpos()[0]}")

p = Path(r"C:\Users\danat\Desktop\dvachbot\site_tgach\templates\board.jinja2")
content = p.read_text(encoding='utf-8')
cleaned = re.sub(r'\{%.*?%\}', '', content, flags=re.DOTALL)
cleaned = re.sub(r'\{\{.*?\}\}', 'placeholder', cleaned, flags=re.DOTALL)
cleaned = re.sub(r'\{#.*?#\}', '', cleaned, flags=re.DOTALL)

bt = BodyTracer()
for tag in ['body', 'html', 'main', 'header', 'footer']:
    matches_start = [(m.start(), content.count('\n', 0, m.start())+1) for m in re.finditer(rf'<{tag}\b', content)]
    matches_end = [(m.start(), content.count('\n', 0, m.start())+1) for m in re.finditer(rf'</{tag}>', content)]
    print(f"<{tag}> starts: {matches_start}, ends: {matches_end}")
