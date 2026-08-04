from typing import List
import re

def split_text(text: str, limit: int) -> list[str]:
    """
    Разбивает длинный текст на части, не превышающие лимит Telegram.
    Добавляет нумерацию (1/N) к частям.
    """
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
            if split_at == -1: # Если пробелов нет, режем по лимиту
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
                 parts[i] = parts[i][:part_limit] # Обрезаем, если нужно
            parts[i] += suffix
    return parts
