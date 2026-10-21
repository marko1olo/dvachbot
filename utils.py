
def split_text(text: str, limit: int) -> list[str]:
    """
    Разбивает длинный текст на части, не превышающие лимит Telegram.
    Добавляет нумерацию (1/N) к частям.
    Если текст содержит HTML-разметку, сохраняет баланс тегов между частями.
    """
    if not text:
        return [""]

    from common.text_chunker import chunk_html_message, count_tg_utf16_units, safe_html_truncate
    from common.text_utils import balance_html_tags

    has_html = "<" in text and ">" in text
    balanced_full = balance_html_tags(text) if has_html else text
    if count_tg_utf16_units(balanced_full) <= limit:
        return [balanced_full]

    # Резервируем место под суффикс нумерации \n(XX/YY)
    suffix_reserve = 25
    effective_limit = max(50, limit - suffix_reserve)
    chunks = chunk_html_message(text, max_chars=effective_limit)
    total = len(chunks)
    if total > 1:
        result = []
        for i, chunk in enumerate(chunks):
            suffix = f"\n({i+1}/{total})"
            balanced = balance_html_tags(chunk) if has_html else chunk
            if count_tg_utf16_units(balanced + suffix) > limit:
                avail = max(10, limit - count_tg_utf16_units(suffix))
                balanced = safe_html_truncate(balanced, max_units=avail, suffix="")
                if has_html:
                    balanced = balance_html_tags(balanced)
            result.append(balanced + suffix)
        return result
    elif total == 1:
        balanced = balance_html_tags(chunks[0]) if has_html else chunks[0]
        if count_tg_utf16_units(balanced) > limit:
            balanced = safe_html_truncate(balanced, max_units=limit, suffix="")
            if has_html:
                balanced = balance_html_tags(balanced)
        return [balanced]
    return [text]
