from __future__ import annotations


import re


def escape_html(text: str) -> str:
    if not text:
        return text
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def convert_site_tags_to_telegram(text: str) -> str:
    """
    Преобразует BB-коды сайта в поддерживаемые HTML-теги Telegram.
    Адаптирует визуальные эффекты под возможности мессенджера.
    """
    if not text:
        return ""
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
