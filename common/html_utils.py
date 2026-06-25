from __future__ import annotations
from collections import Counter


def escape_html(text: str) -> str:
    if not text:
        return text
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def get_truncated_quote_text(quote_text_clean: str) -> str | None:
    if not quote_text_clean:
        return None
    if len(quote_text_clean) > 140:
        return escape_html(quote_text_clean[:140]) + "..."
    return escape_html(quote_text_clean)


def get_quote_media_summary(files_in_quote: list[dict]) -> str | None:
    if not files_in_quote:
        return None

    type_counts = Counter(f.get('type') for f in files_in_quote)

    type_labels = {
        'photo': 'фото',
        'video': 'видео',
        'animation': 'GIF',
        'document': 'doc',
        'audio': 'audio',
        'voice': 'voice',
        'sticker': 'sticker',
        'video_note': 'video note'
    }

    media_counts = []
    for t, label in type_labels.items():
        if type_counts[t] > 0:
            media_counts.append(f"{type_counts[t]} {label}")

    other_count = sum(count for t, count in type_counts.items() if t not in type_labels)
    if other_count > 0:
        media_counts.append(f"{other_count} file")

    if media_counts:
        return f"<i>[{', '.join(media_counts)}]</i>"
    return None
