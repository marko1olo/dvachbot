import re

RE_HTML_TAGS = re.compile(r'<[^>]+>')
RE_YOU_PATTERN = re.compile(r">>(\d+)")
RE_SCRIPT_TAG = re.compile(r'<\s*script\b[^>]*>.*?<\s*/\s*script\s*>', flags=re.IGNORECASE | re.DOTALL)
RE_SCRIPT_SINGLE = re.compile(r'<\s*script\b[^>]*>', flags=re.IGNORECASE)
RE_DANGEROUS_TAGS = re.compile(r'<\s*(iframe|svg|form|object|embed|link)\b[^>]*>.*?<\s*/\s*\1\s*>', flags=re.IGNORECASE | re.DOTALL)
RE_DANGEROUS_SINGLE = re.compile(r'<\s*(iframe|svg|form|object|embed|link)\b[^>]*>', flags=re.IGNORECASE)
# Ловит и закавыченные, и голые значения: on*=alert(1) без кавычек прежний
# паттерн (требовавший ["']) пропускал целиком.
RE_EVENT_HANDLERS = re.compile(
    r'''\s+on\w+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)''',
    flags=re.IGNORECASE,
)
# style Telegram не поддерживает ни на одном теге, а в вебе это вектор
# для оверлеев поверх страницы.
RE_STYLE_ATTR = re.compile(
    r'''\s+style\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)''',
    flags=re.IGNORECASE,
)


def strip_unsafe_attributes(tag: str) -> str:
    """
    Вычищает обработчики событий и style из уже разрешённого тега.

    ALLOWED_TAGS_PATTERN пропускает разрешённые теги ДОСЛОВНО вместе с любыми
    атрибутами (`[^>]*`), поэтому <b onclick="..."> проходил санитайзер целиком.
    RE_EVENT_HANDLERS для этого и объявлялся, но нигде не применялся.

    Не трогаем остальные атрибуты: href, emoji-id, class="language-..." и
    expandable — легальные в Telegram HTML.
    """
    cleaned = RE_EVENT_HANDLERS.sub('', tag)
    return RE_STYLE_ATTR.sub('', cleaned)

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

RE_ATTRS = re.compile(
    r'''\b([a-z0-9_-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))''',
    flags=re.IGNORECASE,
)

def sanitize_html(text: str) -> str:
    if not text: return ""

    text = unwrap_tg_emoji(text)

    parts = []
    last_idx = 0
    open_a_count = 0
    for match in ALLOWED_TAGS_PATTERN.finditer(text):
        start, end = match.span()
        tag_text = match.group(0)
        tag_lower = tag_text.lower()
        
        valid_a_tag = None
        if tag_lower.startswith('<a'):
            for attr_m in RE_ATTRS.finditer(tag_text):
                attr_name = attr_m.group(1).lower()
                if attr_name == "href":
                    val = attr_m.group(2) if attr_m.group(2) is not None else (attr_m.group(3) if attr_m.group(3) is not None else attr_m.group(4))
                    if val and val.lower().strip().startswith(("http://", "https://", "tg://")):
                        valid_a_tag = f'<a href="{val}">'
                    break

        if start > last_idx:
            chunk = text[last_idx:start]
            chunk_escaped = chunk.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            parts.append(chunk_escaped)
        
        if tag_lower.startswith('<a'):
            if valid_a_tag:
                open_a_count += 1
                parts.append(valid_a_tag)
            else:
                parts.append(tag_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))
        elif tag_lower.startswith('</a'):
            if open_a_count > 0:
                open_a_count -= 1
                parts.append('</a>')
            else:
                parts.append(tag_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))
        else:
            parts.append(strip_unsafe_attributes(tag_text))
        last_idx = end
        
    if last_idx < len(text):
        chunk = text[last_idx:]
        chunk_escaped = chunk.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        parts.append(chunk_escaped)

    result = "".join(parts)
    result = re.sub(r'&amp;(lt|gt|amp|quot|#\d+);', r'&\1;', result)
    return result
