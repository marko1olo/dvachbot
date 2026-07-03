import re
import time

keys = [str(i) for i in range(1300)]
start = time.perf_counter()
compiled = {k: re.compile(r'\b' + re.escape(k) + r'\b', re.IGNORECASE) for k in keys}
end = time.perf_counter()
print(f"Time to compile {len(keys)} regexes: {end - start:.4f} seconds")
