import re
import random
import time

# Original implementation
french_replacements_original = [
    (r'\bочень\b', ['très', 'infiniment']),
    (r'\bмой друг\b',['mon cher ami', 'mon cher']),
    (r'\bконечно\b',['bien sûr', 'naturellement', 'sans doute']),
    (r'\bпочему\b', ['pourquoi', 'mon Dieu, pourquoi']),
    (r'\bпрекрасно\b', ['magnifique', 'charmant', 'c’est parfait']),
    (r'\bя люблю\b', ['j’aime', 'je t’aime']),
    (r'\bсогласен\b',['d’accord', 'absolument']),
    (r'\bжизнь\b',['c’est la vie', 'la vie']),
]

def original(text):
    for pattern, replacements in french_replacements_original:
        if random.random() < 0.25:
            text = re.sub(pattern, lambda m: random.choice(replacements), text, flags=re.IGNORECASE)
    return text

# Optimized implementation
FRENCH_REPLACEMENTS_COMPILED = [
    (re.compile(pattern, flags=re.IGNORECASE), replacements)
    for pattern, replacements in french_replacements_original
]

def optimized(text):
    for pattern, replacements in FRENCH_REPLACEMENTS_COMPILED:
        if random.random() < 0.25:
            text = pattern.sub(lambda m: random.choice(replacements), text)
    return text

# Benchmark
test_text = "Я очень люблю жизнь. Конечно, почему бы и нет? Это прекрасно, мой друг! Я согласен."

# Warmup
for _ in range(100):
    original(test_text)
    optimized(test_text)

N = 10000

start = time.perf_counter()
for _ in range(N):
    original(test_text)
orig_time = time.perf_counter() - start

start = time.perf_counter()
for _ in range(N):
    optimized(test_text)
opt_time = time.perf_counter() - start

print(f"Original: {orig_time:.4f}s")
print(f"Optimized: {opt_time:.4f}s")
print(f"Improvement: {(orig_time - opt_time) / orig_time * 100:.2f}%")
