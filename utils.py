import re

def split_text(text: str, limit: int) -> list[str]:
    """
    Разбивает длинный текст на части, не превышающие лимит Telegram.
    Добавляет нумерацию (1/N) к частям.
    """
    if len(text) <= limit:
        return [text]

    def do_split(text, current_limit):
        if current_limit <= 0:
            current_limit = 1
        parts = []
        lines = text.split('\n')
        current_part = ""
        for line in lines:
            if len(current_part) + len(line) + 1 > current_limit:
                if current_part:
                    parts.append(current_part)
                current_part = ""
            while len(line) > current_limit:
                split_at = line.rfind(' ', 0, current_limit)
                if split_at == -1: # Если пробелов нет, режем по лимиту
                    split_at = current_limit
                if split_at == 0:
                    split_at = 1
                parts.append(line[:split_at])
                line = line[split_at:].lstrip()
            if current_part:
                current_part += "\n" + line
            else:
                current_part = line
        if current_part:
            parts.append(current_part)
        return parts

    parts = do_split(text, limit)
    total_parts = len(parts)

    if total_parts > 1:
        max_suffix_len = len(f"\n({total_parts}/{total_parts})")
        if any(len(p) + max_suffix_len > limit for p in parts):
            new_limit = limit - max_suffix_len
            parts = do_split(text, new_limit)
            total_parts = len(parts)
            # Check if suffix length increased due to more parts (e.g., 9 to 10)
            max_suffix_len = len(f"\n({total_parts}/{total_parts})")
            if any(len(p) + max_suffix_len > limit for p in parts):
                new_limit = limit - max_suffix_len
                parts = do_split(text, new_limit)
                total_parts = len(parts)

        for i in range(total_parts):
            parts[i] += f"\n({i+1}/{total_parts})"

    return parts
