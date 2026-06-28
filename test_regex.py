import time
import re
from ukrainian_mode import UKRAINIAN_WORD_REPLACEMENTS, _SORTED_KEYS

start = time.perf_counter()
_BIG_REGEX = re.compile(r'\b(' + '|'.join(re.escape(k) for k in _SORTED_KEYS) + r')\b', re.IGNORECASE)
end = time.perf_counter()
print(f"Compile big regex: {end - start:.4f} seconds")

start = time.perf_counter()
_COMPILED_DICT = {k: re.compile(r'\b' + re.escape(k) + r'\b', re.IGNORECASE) for k in _SORTED_KEYS}
end = time.perf_counter()
print(f"Compile many regexes: {end - start:.4f} seconds")
