import re
import html

URL_PATTERN = re.compile(r'(https?://[^\s<>"\'`]+)')
SPOILER_PATTERN = re.compile(r'\|\|(.*?)\|\|')


def format_post_text(text: str) -> str:
    if not isinstance(text, str):
        return ""

    # --- СУПЕР-ЗАЩИТА ОТ XSS (искажение ключевых слов) ---
    text = re.sub(r"(s)(c)(r)(i)(p)(t)", r"\1\2\3l\5\6", text, flags=re.IGNORECASE)
    text = re.sub(r"(i)(f)(r)(a)(m)(e)", r"l\2\3\4\5\6", text, flags=re.IGNORECASE)
    text = re.sub(r"(e)(x)(p)(r)(e)(s)(s)(i)(o)(n)", r"\1\2\3l\5\6\7\8\9\10", text, flags=re.IGNORECASE)
    text = (
        re.sub(r"(s)(t)(y)(l)(e)", r"\1\2\3\4e", text, flags=re.IGNORECASE)
        .replace("style", "sty1e")
        .replace("STYLE", "STY1E")
    )
    text = re.sub(r"\bon(load|error|click|mouse|key|focus|blur|change|submit)", r"0n\1", text, flags=re.IGNORECASE)

    # --- ЭКРАНИРОВАНИЕ HTML ---
    text = html.escape(text, quote=True)

    # --- ФОРМАТИРОВАНИЕ ---
    text = re.sub(r"&lt;br\s*/?&gt;", "\n", text, flags=re.IGNORECASE)

    processed_text = URL_PATTERN.sub(
        r'<a href="\1" target="_blank" rel="noopener noreferrer">\1</a>', text
    )

    lines = []
    for line in processed_text.split("\n"):
        stripped = line.strip()
        if (stripped.startswith("&gt;") and not stripped.startswith("&gt;&gt;")) or stripped.startswith(">"):
            lines.append(f'<span class="greentext">{line}</span>')
        else:
            lines.append(line)
    processed_text = "<br>".join(lines)

    processed_text = re.sub(
        r"&gt;&gt;/([a-z0-9]+)/(\d+)",
        r'<a href="/\1/res/0#post-\2" class="post-link cross-board-link" data-board-id="\1" data-post-num="\2">&gt;&gt;/\1/\2</a>',
        processed_text,
    )

    processed_text = re.sub(
        r"&gt;&gt;(\d+)",
        r'<a href="#post-\1" class="post-link" data-post-num="\1">&gt;&gt;\1</a>',
        processed_text,
    )

    def btn_replacer(match):
        return f'<a href="{html.escape(match.group(1), quote=True)}" target="_blank" rel="noopener noreferrer" class="btn btn-primary btn-small post-btn">{match.group(2)}</a>'

    def size_replacer(match):
        try:
            return f'<span style="font-size: {max(10, min(30, int(match.group(1))))}px;">{match.group(2)}</span>'
        except ValueError:
            return match.group(2)

    def glitch_replacer(match):
        return f'<span class="effect-glitch" data-text="{match.group(1)}">{match.group(1)}</span>'

    replacements = [
        (r"\[b\](.*?)\[/b\]", r"<b>\1</b>"),
        (r"\[i\](.*?)\[/i\]", r"<i>\1</i>"),
        (r"\[h1\](.*?)\[/h1\]", r'<h3 class="post-heading">\1</h3>'),
        (r"\[btn=(https?://[^\]]+)\](.*?)\[/btn\]", btn_replacer),
        (r"\[size=(\d+)\](.*?)\[/size\]", size_replacer),
        (r"\[s\](.*?)\[/s\]", r"<s>\1</s>"),
        (r"\[u\](.*?)\[/u\]", r"<u>\1</u>"),
        (r"\[code\](.*?)\[/code\]", r"<code>\1</code>"),
        (r"\[shake\](.*?)\[/shake\]", r'<span class="effect-shake">\1</span>'),
        (r"\[rainbow\](.*?)\[/rainbow\]", r'<span class="effect-rainbow">\1</span>'),
        (r"\[blur\](.*?)\[/blur\]", r'<span class="effect-blur">\1</span>'),
        (r"\[glitch\](.*?)\[/glitch\]", glitch_replacer),
    ]

    for pattern, repl in replacements:
        processed_text = re.sub(pattern, repl, processed_text, flags=re.DOTALL)

    processed_text = SPOILER_PATTERN.sub(
        r'<span class="spoiler">\1</span>', processed_text
    )

    return processed_text
