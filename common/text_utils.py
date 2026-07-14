import re

RE_HTML_TAGS = re.compile(r'<[^>]+>')
RE_YOU_PATTERN = re.compile(r">>(\d+)")
RE_SCRIPT_TAG = re.compile(r'<\s*script\b[^>]*>.*?<\s*/\s*script\s*>', flags=re.IGNORECASE | re.DOTALL)
RE_SCRIPT_SINGLE = re.compile(r'<\s*script\b[^>]*>', flags=re.IGNORECASE)
RE_DANGEROUS_TAGS = re.compile(r'<\s*(iframe|svg|form|object|embed|link|a)\b[^>]*>.*?<\s*/\s*\1\s*>', flags=re.IGNORECASE | re.DOTALL)
RE_DANGEROUS_SINGLE = re.compile(r'<\s*(iframe|svg|form|object|embed|link|a)\b[^>]*>', flags=re.IGNORECASE)
RE_EVENT_HANDLERS = re.compile(r'\s+on\w+\s*=\s*["\'].*?["\']', flags=re.IGNORECASE)
RE_A_TAG = re.compile(r'<\s*a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)<\s*/\s*a\s*>', flags=re.IGNORECASE | re.DOTALL)
RE_HTTP = re.compile(r'^https?://', flags=re.IGNORECASE)
RE_WWW = re.compile(r'^www\.', flags=re.IGNORECASE)

def clean_html_tags(text: str) -> str:
    if not text: return text
    return RE_HTML_TAGS.sub('', text)

def sanitize_html(text: str) -> str:
    if not text: return ""

    def link_replacer(match):
        url = match.group(1)
        content = match.group(2)
        clean_url = RE_HTTP.sub('', url)
        clean_url = RE_WWW.sub('', clean_url)
        return f"{content} <i>({clean_url})</i>"

    text = RE_A_TAG.sub(link_replacer, text)

    text = RE_SCRIPT_TAG.sub('', text)
    text = RE_SCRIPT_SINGLE.sub('', text)
    text = RE_DANGEROUS_TAGS.sub('', text)
    text = RE_DANGEROUS_SINGLE.sub('', text)
    text = RE_EVENT_HANDLERS.sub('', text)
    return text
