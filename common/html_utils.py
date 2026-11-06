from __future__ import annotations


import re
from common.latex_utils import normalize_latex


def balance_html_tags(text: str) -> str:
    """Balances unclosed tags and strips orphan closing tags for Telegram HTML parse safety."""
    if not text:
        return ""
    allowed = {'b', 'i', 'u', 's', 'code', 'pre', 'a', 'tg-spoiler', 'tg-emoji', 'blockquote', 'em', 'strong'}
    parts = re.split(r'(</?[a-zA-Z0-9_-]+\b[^>]*>)', text)
    stack = []
    out = []
    for part in parts:
        if part.startswith('<') and part.endswith('>'):
            m = re.match(r'<(/)?([a-zA-Z0-9_-]+)\b([^>]*)>', part)
            if m:
                is_closing = bool(m.group(1))
                tag_name = m.group(2).lower()
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
                else:
                    out.append(part)
            else:
                out.append(part)
        else:
            out.append(part)
    while stack:
        out.append(f'</{stack.pop()}>')
    return "".join(out)


def apply_greentext_formatting(text: str) -> str:
    """
    Применяет форматирование 'Greentext'.
    Работает с уже экранированным HTML-текстом (где > может быть &gt;).
    Предотвращает пересечение тегов с кодовыми блоками (например, <code><b></code></b>).
    """
    if not text:
        return text
    processed_lines = []
    lines = text.split('\n')
    for line in lines:
        stripped_line = line.lstrip()
        if stripped_line.startswith('>') or stripped_line.startswith('&gt;'):
            wrapped = balance_html_tags(f"<code>{line}</code>")
            processed_lines.append(wrapped)
        else:
            processed_lines.append(line)
    return balance_html_tags('\n'.join(processed_lines))


def escape_html(text: str) -> str:
    if not text:
        return text
    return (
        text.replace("\x00", "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )



def convert_site_tags_to_telegram(text: str) -> str:
    """
    Преобразует BB-коды сайта в поддерживаемые HTML-теги Telegram
    и нормализует LaTeX-формулы и математические величины в Unicode.
    """
    if not text:
        return ""
    text = normalize_latex(text)
    text = re.sub(r'\[b\](.*?)\[/b\]', r'<b>\1</b>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\[i\](.*?)\[/i\]', r'<i>\1</i>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\[s\](.*?)\[/s\]', r'<s>\1</s>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\[u\](.*?)\[/u\]', r'<u>\1</u>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\|\|(.*?)\|\|', r'<tg-spoiler>\1</tg-spoiler>', text, flags=re.DOTALL)
    text = re.sub(r'\[blur\](.*?)\[/blur\]', r'<tg-spoiler>\1</tg-spoiler>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\[shake\](.*?)\[/shake\]', r'<i>\1</i>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\[rainbow\](.*?)\[/rainbow\]', r'<code>\1</code>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\[glitch\](.*?)\[/glitch\]', r'<s><code>\1</code></s>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\[code\](.*?)\[/code\]', r'<code>\1</code>', text, flags=re.IGNORECASE | re.DOTALL)
    return text
