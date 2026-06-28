import time
from ukrainian_mode import _stage1_dict_replace

text = "Привет, как дела? Я русский солдат, иду домой, мне нравится борщ и пельмени. Россия вперед! Москва столица!" * 100

start = time.perf_counter()
res, spans = _stage1_dict_replace(text)
end = time.perf_counter()
print(f"Original Time: {end - start:.4f} seconds")
