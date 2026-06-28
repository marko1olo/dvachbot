import timeit
from polish_mode import polish_transform

# Generate some long text for testing
text = "Алексей хороший парень, но иногда он бывает глупый. У него есть жена и много долгов. Он любит пиво и телевизор, а еще мемы и интернет." * 100

def bench():
    # Force _stage_pseudo_polish to run by mocking random
    import random
    original_random = random.random
    random.random = lambda: 0.0  # Force all probability checks to pass

    try:
        polish_transform(text)
    finally:
        random.random = original_random

n_iterations = 100
duration = timeit.timeit(bench, number=n_iterations)
print(f"Time taken for {n_iterations} iterations: {duration:.4f} seconds")
