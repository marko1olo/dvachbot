# The user issue title is: Regex Compilation inside Loop in ukrainian_mode.py
# Wait, look at line 737:
# _COMPILED_DICT = {k: re.compile(r'\b' + re.escape(k) + r'\b', re.IGNORECASE) for k in _SORTED_KEYS}

# A dictionary comprehension is technically a loop!
# Ah! "Regex Compilation inside Loop"
# Oh! The list comprehension / dictionary comprehension is executed at module load time.
# But it compiles 1300 regexes!
# And what if `ukrainian_mode.py` takes a long time to IMPORT?
import time

start = time.perf_counter()
import ukrainian_mode
end = time.perf_counter()
print(f"Import time: {end - start:.4f} seconds")
