import time
import re
import random
from ukrainian_mode import _stage1_dict_replace, _SORTED_KEYS, _get_replacement, _match_case

random.seed(42)
def deterministic_choice(seq): return seq[0]
random.choice = deterministic_choice

_BIG_REGEX = re.compile(r'\b(' + '|'.join(re.escape(k) for k in _SORTED_KEYS) + r')\b', re.IGNORECASE)
_LOWER_KEYS_MAP = {k.lower(): k for k in _SORTED_KEYS}

def _stage1_dict_replace_optimized(text: str) -> tuple[str, set]:
    replaced_spans = set()
    result = []
    last_end = 0

    for m in _BIG_REGEX.finditer(text):
        start = m.start()
        end = m.end()
        original = m.group(0)

        key = _LOWER_KEYS_MAP[original.lower()]

        replacement = _get_replacement(key)
        replacement = _match_case(original, replacement)

        result.append(text[last_end:start])

        current_offset = sum(len(s) for s in result)
        for i in range(current_offset, current_offset + len(replacement)):
            replaced_spans.add(i)

        result.append(replacement)
        last_end = end

    result.append(text[last_end:])
    final_result = "".join(result)

    return final_result, replaced_spans

text = "Привет, как дела? Я русский солдат, иду домой, мне нравится борщ и пельмени. Россия вперед! Москва столица!"

start = time.perf_counter()
for _ in range(1000):
    _stage1_dict_replace(text)
end = time.perf_counter()
print(f"Original Time (1000 runs): {end - start:.4f} seconds")

start = time.perf_counter()
for _ in range(1000):
    _stage1_dict_replace_optimized(text)
end = time.perf_counter()
print(f"Optimized Time (1000 runs): {end - start:.4f} seconds")
