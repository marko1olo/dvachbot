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

def clean_html_for_tg(text: str) -> str:
    if not text: return ''
    
    # First unwrap custom Telegram emoji tags <tg-emoji emoji-id="...">EMOJI</tg-emoji> -> EMOJI
    text = unwrap_tg_emoji(text)

    # Markdown -> HTML
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)', r'<i>\1</i>', text)
    text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)

    # Convert layout/semantic tags to whitespace BEFORE stripping
    # <p>, <br>, <h1-6>, <li>, <div> etc -> newlines
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?p\s*[^>]*>', '\n\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<hr\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?h[1-6]\s*[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?(?:li|dt|dd|tr|td|th)\s*[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?(?:div|section|article|header|footer|main|nav|aside|span|em|strong|ul|ol|table|thead|tbody|tfoot|blockquote|figure|figcaption)\s*[^>]*>', '', text, flags=re.IGNORECASE)

    # Strip ALL remaining non-allowed tags completely
    allowed = {'b', 'i', 'u', 's', 'code', 'pre', 'a', 'tg-spoiler', 'tg-emoji'}

    def _replace_tag(m):
        closing = m.group(1)  # '/' or None
        tag = m.group(2).lower()
        attrs = m.group(3)
        if tag in allowed:
            if closing:
                return f'</{tag}>'
            return f'<{tag}{attrs}>'
        return ''  # strip completely

    text = re.sub(r'<(/?)([a-zA-Z][a-zA-Z0-9_-]*)([^>]*)>', _replace_tag, text)

    # Collapse 3+ newlines to 2
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Balance remaining allowed tags
    parts = re.split(r'(</?[a-zA-Z0-9_-]+\b[^>]*>)', text)
    stack = []
    out = []
    for part in parts:
        if part.startswith('<') and part.endswith('>'):
            m = re.match(r'<(/)?([a-zA-Z]+)\b([^>]*)>', part)
            if m:
                is_closing = bool(m.group(1))
                tag_name = m.group(2).lower()
                attrs = m.group(3)
                if tag_name in allowed:
                    if not is_closing:
                        stack.append(tag_name)
                        out.append(part)
                    else:
                        if stack and stack[-1] == tag_name:
                            stack.pop()
                            out.append(part)
                        elif tag_name in stack:
                            while stack and stack[-1] != tag_name:
                                out.append(f'</{stack.pop()}>')
                            stack.pop()
                            out.append(part)
                        # else: orphan closing tag, skip
                # else: non-allowed, skip
            # else: malformed tag, skip
        else:
            out.append(part)
    while stack:
        out.append(f'</{stack.pop()}>')

    return "".join(out).strip()



def generate_poll_text_display(poll_data: dict) -> str:
    """
    Генерирует текстовое представление опроса с ASCII-барами.
    """
    if not poll_data or 'question' not in poll_data or 'options' not in poll_data:
        return ""
    question = escape_html(poll_data['question'])
    options = poll_data.get('options', [])
    votes = poll_data.get('votes', {})
    total_votes = sum(len(v) for v in votes.values())
    lines = [f"📊 <b>{question.upper()}</b>\n"]
    BAR_LENGTH = 14
    for i, option_text in enumerate(options):
        option_key = str(i)
        vote_count = len(votes.get(option_key, []))
        percentage = (vote_count / total_votes * 100) if total_votes > 0 else 0
        filled_length = int(BAR_LENGTH * vote_count / total_votes) if total_votes > 0 else 0
        bar = '█' * filled_length + '─' * (BAR_LENGTH - filled_length)
        safe_option_text = escape_html(option_text)
        lines.append(f"<code>{i+1}. {safe_option_text}:</code>\n<code>[{bar}] {vote_count} ({percentage:.0f}%)</code>")
    return "\n".join(lines)
