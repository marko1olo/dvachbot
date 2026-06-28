import re
from ukrainian_mode import _stage1_dict_replace

UKRAINIAN_WORD_REPLACEMENTS = {
    "A B": "C D",
    "C": "X",
    "D": "Y"
}

_SORTED_KEYS = sorted(UKRAINIAN_WORD_REPLACEMENTS.keys(), key=len, reverse=True)
_COMPILED_DICT = {k: re.compile(r'\b' + re.escape(k) + r'\b', re.IGNORECASE) for k in _SORTED_KEYS}

def original_stage1(text):
    replaced_spans = set()
    result = text
    for key in _SORTED_KEYS:
        pattern = _COMPILED_DICT[key]
        matches = list(pattern.finditer(result))
        if not matches: continue
        offset = 0
        for m in matches:
            start = m.start() + offset
            end = m.end() + offset
            original = m.group(0)
            replacement = UKRAINIAN_WORD_REPLACEMENTS[key]
            result = result[:start] + replacement + result[end:]
            diff = len(replacement) - len(original)
            offset += diff
            for i in range(start, start + len(replacement)):
                replaced_spans.add(i)
    return result, replaced_spans

print("Original behavior:", original_stage1("A B"))
