from __future__ import annotations


import re

RE_HTML_TAGS = re.compile(r'<[^>]+>')

def clean_html_tags(text: str) -> str:
    if not text:
        return text if text is not None else ""
    return RE_HTML_TAGS.sub('', text)

def escape_html(text: str) -> str:
    if not text:
        return text
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
