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

