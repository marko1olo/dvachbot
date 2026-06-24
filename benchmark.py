import timeit

def list_check():
    ct = 'document'
    return ct in ['photo', 'video', 'animation', 'document', 'audio', 'voice']

def set_check():
    ct = 'document'
    return ct in {'photo', 'video', 'animation', 'document', 'audio', 'voice'}

def tuple_check():
    ct = 'document'
    return ct in ('photo', 'video', 'animation', 'document', 'audio', 'voice')

if __name__ == '__main__':
    n = 10_000_000
    t_list = timeit.timeit('list_check()', globals=globals(), number=n)
    t_tuple = timeit.timeit('tuple_check()', globals=globals(), number=n)
    t_set = timeit.timeit('set_check()', globals=globals(), number=n)

    print(f"List check:  {t_list:.4f}s")
    print(f"Tuple check: {t_tuple:.4f}s")
    print(f"Set check:   {t_set:.4f}s")
