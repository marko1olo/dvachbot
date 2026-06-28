import time
import zaputin_mode

text = "Я сделал эту работу, мы решили что проблем не будет. Тут ошибка. Все упало, но мы купили новое."
# warmup
for _ in range(10):
    zaputin_mode.zaputin_transform(text)

start = time.perf_counter()
for _ in range(10000):
    zaputin_mode.zaputin_transform(text)
end = time.perf_counter()

print(f"Time taken after optimization: {end - start:.5f} seconds")
