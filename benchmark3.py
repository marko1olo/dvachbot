import re
from ukrainian_mode import _stage1_dict_replace
from benchmark2 import _stage1_dict_replace_optimized

text = "Привет, как дела? Я русский солдат, иду домой, мне нравится борщ и пельмени. Россия вперед! Москва столица!"

res1, spans1 = _stage1_dict_replace(text)
res2, spans2 = _stage1_dict_replace_optimized(text)

print(f"Res1: {res1}")
print(f"Res2: {res2}")
