import random
from ukrainian_mode import _stage1_dict_replace

random.seed(42)
text = "Привет, как дела? Я русский солдат, иду домой, мне нравится борщ и пельмени. Россия вперед! Москва столица!"
res1, spans1 = _stage1_dict_replace(text)

random.seed(42)
res2, spans2 = _stage1_dict_replace(text)

print(f"Match: {res1 == res2}")
print(f"Res1: {res1}")
print(f"Res2: {res2}")
