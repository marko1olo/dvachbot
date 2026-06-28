import time
import random
import re

# Mocking the context for benchmark
text = "Это длинный текст с несколькими словами, некоторый из которых красивый, хороший, Иванов, Петров, Алексеев, и длинный-предлинный текст. " * 1000

def original_pseudo_polish(text: str) -> str:
    def _polonize(m):
        word = m.group(0)
        if word.isupper():
            return word
        w = word.replace('ш', 'sz').replace('ч', 'čz').replace('ц', 'č').replace('в', 'w')
        w = w.replace('Ш', 'Sz').replace('Ч', 'Čz').replace('Ц', 'Č').replace('В', 'W')
        w = re.sub(r'ый$', 'ỹ', w)
        w = re.sub(r'ий$', 'i', w)
        w = re.sub(r'ов$', 'ów', w)
        w = re.sub(r'ев$', 'ów', w)
        return w
    return re.sub(r'\b[А-Яа-яЁёA-Za-z]{4,}\b', _polonize, text)

_ADJ_YY_PATTERN = re.compile(r'ый$')
_ADJ_IY_PATTERN = re.compile(r'ий$')
_ADJ_OV_PATTERN = re.compile(r'ов$')
_ADJ_EV_PATTERN = re.compile(r'ев$')
_POLONIZE_WORD_PATTERN = re.compile(r'\b[А-Яа-яЁёA-Za-z]{4,}\b')

def optimized_pseudo_polish(text: str) -> str:
    def _polonize(m):
        word = m.group(0)
        if word.isupper():
            return word
        w = word.replace('ш', 'sz').replace('ч', 'čz').replace('ц', 'č').replace('в', 'w')
        w = w.replace('Ш', 'Sz').replace('Ч', 'Čz').replace('Ц', 'Č').replace('В', 'W')
        w = _ADJ_YY_PATTERN.sub('ỹ', w)
        w = _ADJ_IY_PATTERN.sub('i', w)
        w = _ADJ_OV_PATTERN.sub('ów', w)
        w = _ADJ_EV_PATTERN.sub('ów', w)
        return w
    return _POLONIZE_WORD_PATTERN.sub(_polonize, text)

start = time.time()
for _ in range(100):
    original_pseudo_polish(text)
orig_time = time.time() - start

start = time.time()
for _ in range(100):
    optimized_pseudo_polish(text)
opt_time = time.time() - start

print(f"Original: {orig_time:.4f}s")
print(f"Optimized: {opt_time:.4f}s")
