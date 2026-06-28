from ukrainian_mode import UKRAINIAN_WORD_REPLACEMENTS, _SORTED_KEYS

print(len(_SORTED_KEYS))
for k in _SORTED_KEYS:
    if k.lower() in ["привет", "россия", "москва", "русский"]:
        print(f"Key: {k}, Repl: {UKRAINIAN_WORD_REPLACEMENTS[k]}")
