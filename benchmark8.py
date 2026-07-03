import re
import time
from ukrainian_mode import _stage1_dict_replace, _SORTED_KEYS, _COMPILED_DICT, _get_replacement, _match_case

def _stage1_dict_replace_optimized(text: str) -> tuple[str, set]:
    replaced_spans = set()
    result = text

    for key in _SORTED_KEYS:
        # Search before executing list(finditer)
        pattern = _COMPILED_DICT[key]
        if not pattern.search(result):
            continue

        # The rest is identical to the original code
        matches = list(pattern.finditer(result))
        offset = 0
        for m in matches:
            start = m.start() + offset
            end = m.end() + offset
            original = m.group(0)
            replacement = _get_replacement(key)
            replacement = _match_case(original, replacement)
            result = result[:start] + replacement + result[end:]
            diff = len(replacement) - len(original)
            offset += diff
            for i in range(start, start + len(replacement)):
                replaced_spans.add(i)

    return result, replaced_spans

text = "Привет, как дела? Я русский солдат, иду домой, мне нравится борщ и пельмени. Россия вперед! Москва столица!" * 10

import random
random.seed(42)
def deterministic_choice(seq): return seq[0]
random.choice = deterministic_choice

res1, spans1 = _stage1_dict_replace(text)
res2, spans2 = _stage1_dict_replace_optimized(text)

print(f"Match: {res1 == res2} {spans1 == spans2}")

start = time.perf_counter()
for _ in range(100):
    _stage1_dict_replace(text)
end = time.perf_counter()
print(f"Original Time: {end - start:.4f} seconds")

start = time.perf_counter()
for _ in range(100):
    _stage1_dict_replace_optimized(text)
end = time.perf_counter()
print(f"Optimized Time: {end - start:.4f} seconds")
