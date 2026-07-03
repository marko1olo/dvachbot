from ukrainian_mode import _stage1_dict_replace
from benchmark2 import _stage1_dict_replace_optimized
import random

random.seed(42)
def deterministic_choice(seq): return seq[0]
random.choice = deterministic_choice

for k in ["время", "болото", "артиллерия", "измена"]:
    res1, _ = _stage1_dict_replace(k)
    res2, _ = _stage1_dict_replace_optimized(k)
    print(f"Key: {k}")
    print(f"Original: {res1}")
    print(f"Optimized: {res2}")
    print("-" * 20)
