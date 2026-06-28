import benchmark2
from benchmark2 import _stage1_dict_replace, _stage1_dict_replace_optimized
from ukrainian_mode import UKRAINIAN_WORD_REPLACEMENTS, _SORTED_KEYS, _COMPILED_DICT

def get_mismatches(text):
    import random
    random.seed(42)
    def deterministic_choice(seq): return seq[0]
    random.choice = deterministic_choice

    res1, _ = _stage1_dict_replace(text)
    res2, _ = _stage1_dict_replace_optimized(text)
    return res1 != res2

import sys
sys.path.append('.')
from ukrainian_mode import UKRAINIAN_WORD_REPLACEMENTS
for k in UKRAINIAN_WORD_REPLACEMENTS:
    if get_mismatches(k):
        print("Mismatch on key:", k)
