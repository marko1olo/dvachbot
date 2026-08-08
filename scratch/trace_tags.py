import html.parser
import re
from pathlib import Path

class TracingParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.self_closing = {'img', 'input', 'br', 'hr', 'meta', 'link', 'source', 'param', 'embed'}
        
    def handle_starttag(self, tag, attrs):
        if tag not in self.self_closing:
            self.stack.append((tag, self.getpos()))
            
    def handle_endtag(self, tag):
        if tag in self.self_closing:
            return
        if not self.stack:
            print(f"Endtag </{tag}> at line {self.getpos()[0]} with empty stack")
            return
        if self.stack[-1][0] == tag:
            self.stack.pop()
        else:
            print(f"Mismatched closing tag </{tag}> at line {self.getpos()[0]}. Open tag stack top: {self.stack[-1]}")
            # check if tag is in stack
            stack_tags = [t[0] for t in self.stack]
            if tag in stack_tags:
                idx = len(stack_tags) - 1 - stack_tags[::-1].index(tag)
                print(f"  --> Tag <{tag}> was opened at {self.stack[idx][1]}, but unclosed tags in between: {self.stack[idx+1:]}")

p = Path(r"C:\Users\danat\Desktop\dvachbot\site_tgach\templates\board.jinja2")
content = p.read_text(encoding='utf-8')
cleaned = re.sub(r'\{%.*?%\}', '', content, flags=re.DOTALL)
cleaned = re.sub(r'\{\{.*?\}\}', 'placeholder', cleaned, flags=re.DOTALL)
cleaned = re.sub(r'\{#.*?#\}', '', cleaned, flags=re.DOTALL)

tp = TracingParser()
tp.feed(cleaned)
