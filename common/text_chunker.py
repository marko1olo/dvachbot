import re
from typing import List, Tuple

# Supported Telegram HTML tags
TG_ALLOWED_TAGS = {
    "b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
    "span", "tg-spoiler", "a", "tg-emoji", "code", "pre", "blockquote"
}

# Simple pattern without nested quantifiers — no ReDoS risk
TAG_PATTERN = re.compile(r"</?([a-zA-Z0-9_-]+)[^>]*>")
HTML_ENTITY_PATTERN = re.compile(r"&[a-zA-Z0-9#]+;")


def count_tg_utf16_units(text: str) -> int:
    """
    Returns exact count of UTF-16 code units for Telegram message limits.
    Characters in BMP (<= 0xFFFF) count as 1 code unit.
    Astral characters (> 0xFFFF, e.g. emojis) count as 2 code units.
    """
    if not text:
        return 0
    return len(text.encode("utf-16-le")) // 2


def utf16_to_char_index(s: str, max_units: int) -> int:
    """
    Finds maximum character index such that count_tg_utf16_units(s[:idx]) <= max_units.
    """
    if not s or max_units <= 0:
        return 0
    if len(s) <= max_units and count_tg_utf16_units(s) <= max_units:
        return len(s)

    low = 0
    high = len(s)
    while low < high:
        mid = (low + high + 1) // 2
        if count_tg_utf16_units(s[:mid]) <= max_units:
            low = mid
        else:
            high = mid - 1
    return low


def get_open_tags(html_text: str) -> List[Tuple[str, str]]:
    """
    Inspects an HTML fragment and returns the stack of currently open tags
    as a list of (tag_name, full_opening_tag_str) tuples.
    """
    stack: List[Tuple[str, str]] = []
    for match in TAG_PATTERN.finditer(html_text):
        tag_str = match.group(0)
        tag_name = match.group(1).lower()

        if tag_name not in TG_ALLOWED_TAGS:
            continue
        if tag_str.endswith("/>"):
            continue

        if tag_str.startswith("</"):
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] == tag_name:
                    stack.pop(i)
                    break
        else:
            stack.append((tag_name, tag_str))
    return stack


def get_open_tags_incremental(
    starting_stack: List[Tuple[str, str]], html_fragment: str
) -> List[Tuple[str, str]]:
    """
    Extends an existing open-tag stack by processing html_fragment.
    Returns the resulting stack without mutating starting_stack.
    """
    stack = list(starting_stack)
    for match in TAG_PATTERN.finditer(html_fragment):
        tag_str = match.group(0)
        tag_name = match.group(1).lower()

        if tag_name not in TG_ALLOWED_TAGS:
            continue
        if tag_str.endswith("/>"):
            continue

        if tag_str.startswith("</"):
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] == tag_name:
                    stack.pop(i)
                    break
        else:
            stack.append((tag_name, tag_str))
    return stack


def build_closing_tags(open_tags: List[Tuple[str, str]]) -> str:
    """Closes currently open tags in reverse order of opening."""
    return "".join(f"</{tag_name}>" for tag_name, _ in reversed(open_tags))


def build_reopening_tags(open_tags: List[Tuple[str, str]]) -> str:
    """Reopens tags in forward order of opening."""
    return "".join(full_str for _, full_str in open_tags)


def safe_html_truncate(text: str, max_units: int = 4000, suffix: str = "…") -> str:
    """
    Safely truncates HTML text to fit Telegram's UTF-16 code unit limit,
    guaranteeing that all open HTML tags are cleanly closed and no tags/entities
    are sliced across boundaries.
    """
    if not text:
        return ""
    if count_tg_utf16_units(text) <= max_units:
        return text

    suffix_units = count_tg_utf16_units(suffix)
    effective_limit = max(10, max_units - suffix_units - 50)
    limit_idx = utf16_to_char_index(text, effective_limit)

    # Search for natural boundary
    split_idx = text.rfind("\n", 0, limit_idx)
    if split_idx == -1 or split_idx < limit_idx // 2:
        split_idx = text.rfind(" ", 0, limit_idx)
    if split_idx == -1 or split_idx < limit_idx // 3:
        split_idx = limit_idx

    # Guard against splitting inside tag or entity
    last_lt = text.rfind("<", 0, split_idx)
    last_gt = text.rfind(">", 0, split_idx)
    if last_lt > last_gt:
        split_idx = last_lt

    last_amp = text.rfind("&", 0, split_idx)
    last_semi = text.rfind(";", 0, split_idx)
    if last_amp > last_semi and (split_idx - last_amp) < 12:
        split_idx = last_amp

    if split_idx <= 0:
        split_idx = max(1, limit_idx)

    raw_part = text[:split_idx].rstrip()
    open_tags = get_open_tags(raw_part)
    closing = build_closing_tags(open_tags)

    res = raw_part + suffix + closing
    max_trim_iters = 100
    trim_iters = 0
    while count_tg_utf16_units(res) > max_units and split_idx > 1 and trim_iters < max_trim_iters:
        trim_iters += 1
        split_idx = max(1, split_idx - 50)
        raw_part = text[:split_idx].rstrip()
        open_tags = get_open_tags(raw_part)
        closing = build_closing_tags(open_tags)
        res = raw_part + suffix + closing

    return res


def _find_split_idx(source: str, limit_char_idx: int) -> int:
    """
    Finds the best split position within source[0:limit_char_idx].
    Tries paragraph break, newline, sentence end, word boundary, hard boundary.
    Returns a position > 0 and <= limit_char_idx.
    """
    # 1. Paragraph break \n\n
    split_idx = source.rfind("\n\n", 0, limit_char_idx)
    if split_idx != -1 and split_idx >= limit_char_idx // 3:
        return split_idx + 2  # include the \n\n so lstrip() removes it cleanly

    # 2. Newline \n
    split_idx = source.rfind("\n", 0, limit_char_idx)
    if split_idx != -1 and split_idx >= limit_char_idx // 3:
        return split_idx + 1

    # 3. Sentence end (.!?) followed by space — find last occurrence
    best_sent = -1
    for m in re.finditer(r"[.!?]\s+", source[:limit_char_idx]):
        best_sent = m.end()
    if best_sent != -1 and best_sent >= limit_char_idx // 3:
        return best_sent

    # 4. Word boundary
    split_idx = source.rfind(" ", 0, limit_char_idx)
    if split_idx != -1 and split_idx >= limit_char_idx // 3:
        return split_idx + 1

    # 5. Hard boundary at limit
    return max(1, limit_char_idx)


def chunk_html_message(
    text: str,
    max_chars: int = 4000,
    max_units: int | None = None
) -> List[str]:
    """
    Proactively chunks an HTML message into pieces under max_chars (Telegram UTF-16 limit).
    Preserves and balances HTML tags across chunk boundaries.

    Key design: advances a pointer `pos` through the ORIGINAL text — never mutates/prepends
    to a working copy. This guarantees O(n) progress and prevents infinite loops.
    Inherited open tags from the previous chunk are tracked separately and used only
    for building the prefix/suffix of each output chunk.
    """
    if max_units is not None:
        max_chars = max_units

    if not text:
        return [""]
    if count_tg_utf16_units(text) <= max_chars:
        return [text]

    chunks: List[str] = []
    pos = 0  # cursor in original text
    inherited_open_tags: List[Tuple[str, str]] = []  # context carried from previous chunk

    while pos < len(text):
        # Skip leading whitespace between chunks
        while pos < len(text) and text[pos] in " \t\n\r":
            pos += 1
        if pos >= len(text):
            break

        source = text[pos:]

        # Build prefix from inherited context
        prefix = build_reopening_tags(inherited_open_tags)
        prefix_units = count_tg_utf16_units(prefix)

        # Reserve space for closing tags of inherited context + any newly opened tags
        # Worst case: each tag ~15 chars. Cap pessimistically at 40 tags × 15 = 600 chars.
        max_close_reserve = min(600, (len(inherited_open_tags) + 10) * 15)
        available_units = max_chars - prefix_units - max_close_reserve

        if available_units < 20:
            # Inherited context is too deep/wide; reset it and emit a bare reset chunk
            # This is a last-resort safety valve.
            inherited_open_tags = []
            prefix = ""
            prefix_units = 0
            available_units = max_chars - 50

        limit_char_idx = utf16_to_char_index(source, available_units)
        if limit_char_idx <= 0:
            limit_char_idx = min(1, len(source))

        # Guard: don't split inside an HTML tag (<...>)
        split_candidate = _find_split_idx(source, limit_char_idx)

        last_lt = source.rfind("<", 0, split_candidate)
        last_gt = source.rfind(">", 0, split_candidate)
        if last_lt > last_gt:
            # We'd cut inside a tag — back up to before the tag
            split_candidate = last_lt if last_lt > 0 else split_candidate

        # Guard: don't split inside an HTML entity (&...;)
        last_amp = source.rfind("&", 0, split_candidate)
        last_semi = source.rfind(";", 0, split_candidate)
        if last_amp > last_semi and (split_candidate - last_amp) < 12:
            split_candidate = last_amp if last_amp > 0 else split_candidate

        # Ensure at least 1 char of progress no matter what
        split_candidate = max(1, min(split_candidate, len(source)))

        # Content slice from original text
        raw_content = source[:split_candidate].rstrip()

        # Compute resulting open-tag state after this content
        new_open_tags = get_open_tags_incremental(inherited_open_tags, raw_content)
        closing = build_closing_tags(new_open_tags)

        chunk = prefix + raw_content + closing

        # Fine-tune: if chunk still exceeds limit (tag overhead underestimated), trim
        trim_iters = 0
        while count_tg_utf16_units(chunk) > max_chars and split_candidate > 1 and trim_iters < 50:
            trim_iters += 1
            split_candidate = max(1, split_candidate - 30)
            raw_content = source[:split_candidate].rstrip()
            new_open_tags = get_open_tags_incremental(inherited_open_tags, raw_content)
            closing = build_closing_tags(new_open_tags)
            chunk = prefix + raw_content + closing

        if chunk.strip():
            chunks.append(chunk)

        # Advance position in original text — guaranteed progress
        pos += split_candidate

        # Carry forward open-tag context (without closing tags)
        inherited_open_tags = new_open_tags

    if not chunks:
        return [text]

    return chunks
