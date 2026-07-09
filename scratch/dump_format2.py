def format_post_text(text: str) -> str:
    if not isinstance(text, str):
        return ""

    # --- СУПЕР-ЗАЩИТА ОТ XSS (искажение ключевых слов) ---
    # script -> sclipt (i -> l)
    text = re.sub(r"(s)(c)(r)(i)(p)(t)", r"\1\2\3l\5\6", text, flags=re.IGNORECASE)
    # iframe -> lframe (i -> l)
    text = re.sub(r"(i)(f)(r)(a)(m)(e)", r"l\2\3\4\5\6", text, flags=re.IGNORECASE)
    # expression -> explession (для CSS) (r -> l чтобы сломать слово)
    text = re.sub(
        r"(e)(x)(p)(r)(e)(s)(s)(i)(o)(n)",
        r"\1\2\3l\5\6\7\8\9\10",
        text,
        flags=re.IGNORECASE,
    )
    # style -> sty1e (l -> 1)
    text = (
        re.sub(r"(s)(t)(y)(l)(e)", r"\1\2\3\4e", text, flags=re.IGNORECASE)
        .replace("style", "sty1e")
        .replace("STYLE", "STY1E")
    )
    # События (onload, onerror, onclick...) -> 0nload...
    text = re.sub(
        r"\bon(load|error|click|mouse|key|focus|blur|change|submit)",
        r"0n\1",
        text,
        flags=re.IGNORECASE,
    )
    # javascript: -> javasclipt: (уже покрыто заменой script, но на всякий случай)

    # --- ЭКРАНИРОВАНИЕ HTML ---
    # Превращает < > " ' & в безопасные сущности
    text = html.escape(text, quote=True)

    # --- ФОРМАТИРОВАНИЕ ---
    text = re.sub(r"&lt;br\s*/?&gt;", "\n", text, flags=re.IGNORECASE)

    processed_text = URL_PATTERN.sub(
        r'<a href="\1" target="_blank" rel="noopener noreferrer">\1</a>', text
    )

    lines = []
    for line in processed_text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("&gt;") and not stripped.startswith("&gt;&gt;"):
            lines.append(f'<span class="greentext">{line}</span>')
        elif stripped.startswith(">"):
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

    processed_text = re.sub(
        r"\[b\](.*?)\[/b\]", r"<b>\1</b>", processed_text, flags=re.DOTALL
    )
    processed_text = re.sub(
        r"\[i\](.*?)\[/i\]", r"<i>\1</i>", processed_text, flags=re.DOTALL
    )
    processed_text = re.sub(
        r"\[h1\](.*?)\[/h1\]",
        r'<h3 class="post-heading">\1</h3>',
        processed_text,
        flags=re.DOTALL,
    )

    def btn_replacer(match):
        url = match.group(1)
        safe_url = html.escape(url, quote=True)
        text = match.group(2)
        return f'<a href="{safe_url}" target="_blank" rel="noopener noreferrer" class="btn btn-primary btn-small post-btn">{text}</a>'

    processed_text = re.sub(
        r"\[btn=(https?://[^\]]+)\](.*?)\[/btn\]",
        btn_replacer,
        processed_text,
        flags=re.DOTALL,
    )

    def size_replacer(match):
        try:
            s = int(match.group(1))
            s = max(10, min(30, s))
            return f'<span style="font-size: {s}px;">{match.group(2)}</span>'
        except:
            return match.group(2)

    processed_text = re.sub(
        r"\[size=(\d+)\](.*?)\[/size\]", size_replacer, processed_text, flags=re.DOTALL
    )
    processed_text = re.sub(
        r"\[s\](.*?)\[/s\]", r"<s>\1</s>", processed_text, flags=re.DOTALL
    )
    processed_text = re.sub(
        r"\[u\](.*?)\[/u\]", r"<u>\1</u>", processed_text, flags=re.DOTALL
    )
    processed_text = re.sub(
        r"\[code\](.*?)\[/code\]", r"<code>\1</code>", processed_text, flags=re.DOTALL
    )

    processed_text = re.sub(
        r"\[shake\](.*?)\[/shake\]",
        r'<span class="effect-shake">\1</span>',
        processed_text,
        flags=re.DOTALL,
    )
    processed_text = re.sub(
        r"\[rainbow\](.*?)\[/rainbow\]",
        r'<span class="effect-rainbow">\1</span>',
        processed_text,
        flags=re.DOTALL,
    )
    processed_text = re.sub(
        r"\[blur\](.*?)\[/blur\]",
        r'<span class="effect-blur">\1</span>',
        processed_text,
        flags=re.DOTALL,
    )

    def _glitch_replacer(match):
        content = match.group(1)
        return f'<span class="effect-glitch" data-text="{content}">{content}</span>'

    processed_text = re.sub(
        r"\[glitch\](.*?)\[/glitch\]", _glitch_replacer, processed_text, flags=re.DOTALL
    )
    processed_text = SPOILER_PATTERN.sub(
        r'<span class="spoiler">\1</span>', processed_text
    )

    return processed_text


