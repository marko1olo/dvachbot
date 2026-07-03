import time
import re
from ukrainian_mode import _stage1_dict_replace, UKRAINIAN_WORD_REPLACEMENTS, _SORTED_KEYS, _get_replacement, _match_case

# Create the single big regex
_BIG_REGEX = re.compile(r'\b(' + '|'.join(re.escape(k) for k in _SORTED_KEYS) + r')\b', re.IGNORECASE)

# Mapping dictionary for the single big regex, ignoring case
_LOWER_KEYS_MAP = {k.lower(): k for k in _SORTED_KEYS}

def _stage1_dict_replace_optimized(text: str) -> tuple[str, set]:
    replaced_spans = set()
    result = []
    last_end = 0

    for m in _BIG_REGEX.finditer(text):
        start = m.start()
        end = m.end()
        original = m.group(0)

        # We need the original key from the dictionary, preserving case in the mapping
        key = _LOWER_KEYS_MAP[original.lower()]

        replacement = _get_replacement(key)
        replacement = _match_case(original, replacement)

        # Append unchanged text
        result.append(text[last_end:start])

        # Mark spans (relative to the new string)
        current_offset = sum(len(s) for s in result)
        for i in range(current_offset, current_offset + len(replacement)):
            replaced_spans.add(i)

        result.append(replacement)
        last_end = end

    result.append(text[last_end:])
    final_result = "".join(result)

    return final_result, replaced_spans

text = "Привет, как дела? Я русский солдат, иду домой, мне нравится борщ и пельмени. Россия вперед! Москва столица!" * 100

start = time.perf_counter()
res1, spans1 = _stage1_dict_replace(text)
end1 = time.perf_counter()
print(f"Original Time: {end1 - start:.4f} seconds")

start = time.perf_counter()
res2, spans2 = _stage1_dict_replace_optimized(text)
end2 = time.perf_counter()
print(f"Optimized Time: {end2 - start:.4f} seconds")

print(f"Results match: {res1 == res2}")
print(f"Spans match: {spans1 == spans2}")
