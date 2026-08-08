import html.parser
from pathlib import Path

class HTMLValidator(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.errors = []
        self.stack = []
        self.self_closing = {'img', 'input', 'br', 'hr', 'meta', 'link', 'source', 'param', 'embed'}
        
    def handle_starttag(self, tag, attrs):
        if tag not in self.self_closing:
            self.stack.append(tag)
            
    def handle_endtag(self, tag):
        if tag in self.self_closing:
            return
        if not self.stack:
            self.errors.append(f"Unexpected closing tag </{tag}> with empty stack")
        elif self.stack[-1] == tag:
            self.stack.pop()
        else:
            self.errors.append(f"Mismatched closing tag </{tag}>, expected </{self.stack[-1]}>")

templates = ['catalog.jinja2', 'thread.jinja2', 'board.jinja2', 'gallery.jinja2']
templates_dir = Path(r"C:\Users\danat\Desktop\dvachbot\site_tgach\templates")

for t_name in templates:
    p = templates_dir / t_name
    content = p.read_text(encoding='utf-8')
    # strip jinja tags for basic HTML parsing
    import re
    cleaned = re.sub(r'\{%.*?%\}', '', content, flags=re.DOTALL)
    cleaned = re.sub(r'\{\{.*?\}\}', 'placeholder', cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'\{#.*?#\}', '', cleaned, flags=re.DOTALL)
    
    parser = HTMLValidator()
    try:
        parser.feed(cleaned)
        print(f"{t_name}: {len(parser.errors)} errors, unclosed tags remaining: {parser.stack}")
        for err in parser.errors[:5]:
            print(f"  - {err}")
    except Exception as e:
        print(f"{t_name}: Parsing exception: {e}")
