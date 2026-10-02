from typing import List
import re

def split_text(text: str, limit: int) -> list[str]:
    """
    Разбивает длинный текст на части, не превышающие лимит Telegram.
    Добавляет нумерацию (1/N) к частям.
    Если текст содержит HTML-разметку, сохраняет баланс тегов между частями.
    """
    if not text:
        return [""]

    # Если в тексте есть HTML-теги, используем HTML-aware разбиение
    if "<" in text and ">" in text:
        try:
            from common.text_chunker import chunk_html_message, count_tg_utf16_units, safe_html_truncate
            from common.text_utils import balance_html_tags

            # Если полный текст после балансировки тегов помещается целиком в лимит
            balanced_full = balance_html_tags(text)
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
                    balanced = balance_html_tags(chunk)
                    if count_tg_utf16_units(balanced + suffix) > limit:
                        avail = max(10, limit - count_tg_utf16_units(suffix))
                        balanced = safe_html_truncate(balanced, max_units=avail, suffix="")
                        balanced = balance_html_tags(balanced)
                    result.append(balanced + suffix)
                return result
            elif total == 1:
                balanced = balance_html_tags(chunks[0])
                if count_tg_utf16_units(balanced) > limit:
                    balanced = safe_html_truncate(balanced, max_units=limit, suffix="")
                    balanced = balance_html_tags(balanced)
                return [balanced]
        except Exception:
            pass

    if len(text) <= limit:
        return [text]

    parts = []
    lines = text.split('\n')
    current_part = ""
    for line in lines:
        if len(current_part) + len(line) + 1 > limit:
            if current_part:
                parts.append(current_part)
            current_part = ""
        while len(line) > limit:
            split_at = line.rfind(' ', 0, limit)
            if split_at <= 0:  # Если пробелов нет, режем по лимиту
                split_at = limit
            parts.append(line[:split_at])
            line = line[split_at:].lstrip()
        if current_part:
            current_part += "\n" + line
        else:
            current_part = line
    if current_part:
        parts.append(current_part)
    total_parts = len(parts)
    if total_parts > 1:
        for i in range(total_parts):
            suffix = f"\n({i+1}/{total_parts})"
            part_limit = limit - len(suffix)
            if len(parts[i]) > part_limit:
                 parts[i] = parts[i][:part_limit]  # Обрезаем, если нужно
            parts[i] += suffix
    return parts
