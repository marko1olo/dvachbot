import re
import time
from ukrainian_mode import _stage1_dict_replace, _SORTED_KEYS, _COMPILED_DICT, _get_replacement, _match_case

text = "Привет, как дела? Я русский солдат, иду домой, мне нравится борщ и пельмени. Россия вперед! Москва столица!" * 10

# A faster search loop with one big regex to PRE-FILTER.

_BIG_REGEX_PATTERN = r'(?i)\b(' + '|'.join(re.escape(k) for k in _SORTED_KEYS) + r')\b'
_BIG_REGEX = re.compile(_BIG_REGEX_PATTERN)

def _stage1_dict_replace_optimized3(text: str) -> tuple[str, set]:
    replaced_spans = set()
    result = text

    # Pre-filter: find which keys are actually in the string
    # We must do this iteratively if replacements add new keys.
    # But for a single pass:

    # Actually, the original implementation runs through ALL _SORTED_KEYS sequentially.
    # If we just do:
    for key in _SORTED_KEYS:
        # Check if the word is in the text first using simple string match!
        # string match is much faster than regex.
        # It's case insensitive, so we can check against a lowercased result.
        pass
