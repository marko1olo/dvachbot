import timeit
import re

text = "Алексей хороший парень, но иногда он бывает глупый. У него есть жена и много долгов. Он любит пиво и телевизор, а еще мемы и интернет." * 100

def bench_original():
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


_SUFFIX_YJ_PATTERN = re.compile(r'ый$')
_SUFFIX_IJ_PATTERN = re.compile(r'ий$')
_SUFFIX_OV_PATTERN = re.compile(r'ов$')
_SUFFIX_EV_PATTERN = re.compile(r'ев$')
_POLONIZE_WORD_PATTERN = re.compile(r'\b[А-Яа-яЁёA-Za-z]{4,}\b')

def bench_optimized():
    def _polonize(m):
        word = m.group(0)
        if word.isupper():
            return word
        w = word.replace('ш', 'sz').replace('ч', 'čz').replace('ц', 'č').replace('в', 'w')
        w = w.replace('Ш', 'Sz').replace('Ч', 'Čz').replace('Ц', 'Č').replace('В', 'W')
        w = _SUFFIX_YJ_PATTERN.sub('ỹ', w)
        w = _SUFFIX_IJ_PATTERN.sub('i', w)
        w = _SUFFIX_OV_PATTERN.sub('ów', w)
        w = _SUFFIX_EV_PATTERN.sub('ów', w)
        return w
    return _POLONIZE_WORD_PATTERN.sub(_polonize, text)


n_iterations = 1000
duration_orig = timeit.timeit(bench_original, number=n_iterations)
duration_opt = timeit.timeit(bench_optimized, number=n_iterations)

print(f"Original: {duration_orig:.4f} seconds")
print(f"Optimized: {duration_opt:.4f} seconds")
