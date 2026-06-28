import benchmark5
from benchmark5 import _stage1_dict_replace, _stage1_dict_replace_optimized
from ukrainian_mode import UKRAINIAN_WORD_REPLACEMENTS, _SORTED_KEYS, _COMPILED_DICT

# Do we have cascaded replaces in real data?
count = 0
for k1 in _SORTED_KEYS:
    for v1 in UKRAINIAN_WORD_REPLACEMENTS[k1] if isinstance(UKRAINIAN_WORD_REPLACEMENTS[k1], list) else [UKRAINIAN_WORD_REPLACEMENTS[k1]]:
        # See if v1 contains any other key that would be matched in subsequent iterations
        for k2 in _SORTED_KEYS:
            if k1 != k2 and _COMPILED_DICT[k2].search(v1):
                count += 1
                # print(f"Cascaded: {k1} -> {v1} -> {k2}")

print(f"Total cascaded possibilities: {count}")
