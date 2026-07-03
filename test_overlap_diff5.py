from ukrainian_mode import UKRAINIAN_WORD_REPLACEMENTS, _SORTED_KEYS

def cascade_trace(word):
    print(f"Tracing '{word}':")
    text = word
    for key in _SORTED_KEYS:
        import re
        pattern = re.compile(r'\b' + re.escape(key) + r'\b', re.IGNORECASE)
        if pattern.search(text):
            old = text
            text = pattern.sub(UKRAINIAN_WORD_REPLACEMENTS[key][0] if isinstance(UKRAINIAN_WORD_REPLACEMENTS[key], list) else UKRAINIAN_WORD_REPLACEMENTS[key], text)
            print(f"  Matched '{key}' -> '{text}'")

cascade_trace("время")
cascade_trace("болото")
cascade_trace("артиллерия")
cascade_trace("измена")
