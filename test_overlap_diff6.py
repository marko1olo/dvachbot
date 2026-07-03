# If I use one big regex: `re.compile(r'\b(' + '|'.join(re.escape(k) for k in _SORTED_KEYS) + r')\b', re.IGNORECASE)`
# What if two words match? The regex will match the first one in the alternation.
# Since we sorted by length descending, `|`.join matches longest strings first, which is equivalent to testing longest keys first.
# Wait, why did the single regex approach fail on "время", "болото", etc.?
# Because in the original implementation, after replacing "время" with "час", the updated string is then tested against ALL SUBSEQUENT KEYS.
# "час" is another key in the dict. So "час" gets matched when the loop reaches it, and replaced with "година"!
# A single big regex pass does NOT re-scan the replaced text for subsequent matches.
