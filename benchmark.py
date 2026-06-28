import timeit

def original_version(boards):
    return [b.strip() for b in boards.split(',') if b.strip()]

def optimized_version(boards):
    return [stripped for b in boards.split(',') if (stripped := b.strip())]

boards = "b" * 100 + ", " + "a" * 100 + ", " + "  " + ", " + "gd" * 50
boards = (boards + ",") * 1000

print("Original:", timeit.timeit(lambda: original_version(boards), number=10000))
print("Optimized:", timeit.timeit(lambda: optimized_version(boards), number=10000))
