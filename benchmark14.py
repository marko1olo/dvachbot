import time
# Since ukrainian_mode.py ALREADY has the optimization we applied, both functions are the same now!
# That's why the time is the same. Let's make sure our optimization works.
from ukrainian_mode import _stage1_dict_replace
text = "Привет, как дела? Я русский солдат, иду домой, мне нравится борщ и пельмени. Россия вперед! Москва столица!" * 10
start = time.perf_counter()
for _ in range(100):
    _stage1_dict_replace(text)
end = time.perf_counter()
print(f"Current optimized time: {end - start:.4f} seconds")
