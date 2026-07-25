import re

RE_HTML_TAGS = re.compile(r'<[^>]+>')
RE_YOU_PATTERN = re.compile(r">>(\d+)")
RE_SCRIPT_TAG = re.compile(r'<\s*script\b[^>]*>.*?<\s*/\s*script\s*>', flags=re.IGNORECASE | re.DOTALL)
RE_SCRIPT_SINGLE = re.compile(r'<\s*script\b[^>]*>', flags=re.IGNORECASE)
RE_DANGEROUS_TAGS = re.compile(r'<\s*(iframe|svg|form|object|embed|link)\b[^>]*>.*?<\s*/\s*\1\s*>', flags=re.IGNORECASE | re.DOTALL)
RE_DANGEROUS_SINGLE = re.compile(r'<\s*(iframe|svg|form|object|embed|link)\b[^>]*>', flags=re.IGNORECASE)
RE_EVENT_HANDLERS = re.compile(r'\s+on\w+\s*=\s*["\'].*?["\']', flags=re.IGNORECASE)

RE_TG_EMOJI_FULL = re.compile(r'<tg-emoji\b[^>]*>(.*?)</tg-emoji>', flags=re.IGNORECASE | re.DOTALL)
RE_TG_EMOJI_STRIP = re.compile(r'</?tg-emoji\b[^>]*>', flags=re.IGNORECASE)

def unwrap_tg_emoji(text: str) -> str:
    if not text: return text
    text = RE_TG_EMOJI_FULL.sub(r'\1', text)
    text = RE_TG_EMOJI_STRIP.sub('', text)
    return text

ALLOWED_TAGS_PATTERN = re.compile(
    r'</?(?:b|i|u|s|code|pre|blockquote|tg-spoiler|tg-emoji|em|strong)\b[^>]*>|'
    r'<\s*a\s+[^>]*href=["\'](?:https?://|tg://)[^"\']+["\'][^>]*>|'
    r'</\s*a\s*>',
    flags=re.IGNORECASE
)

def clean_html_tags(text: str) -> str:
    if not text: return text
    text = unwrap_tg_emoji(text)
    return RE_HTML_TAGS.sub('', text)

def sanitize_html(text: str) -> str:
    if not text: return ""

    text = unwrap_tg_emoji(text)

    parts = []
    last_idx = 0
    for match in ALLOWED_TAGS_PATTERN.finditer(text):
        start, end = match.span()
        if start > last_idx:
            chunk = text[last_idx:start]
            chunk_escaped = chunk.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            parts.append(chunk_escaped)
        parts.append(match.group(0))
        last_idx = end
        
    if last_idx < len(text):
        chunk = text[last_idx:]
        chunk_escaped = chunk.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        parts.append(chunk_escaped)

    result = "".join(parts)
    result = re.sub(r'&amp;(lt|gt|amp|quot|#\d+);', r'&\1;', result)
    return result
