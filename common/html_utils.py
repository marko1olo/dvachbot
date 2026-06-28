from __future__ import annotations


def escape_html(text: str) -> str:
    if not text:
        return text
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

def _safe_len(value) -> int:
    try:
        return len(value)
    except Exception:
        return -1
