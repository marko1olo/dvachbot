import timeit

setup = 'path = "/some/long/path/with/admin/inside"'

test_list = "any(x in path for x in ['.zip', '.tar', '.gz', '.sql', '.dump', '.bak', 'backup', 'admin', '.env', '.old'])"
test_set = "any(x in path for x in {'.zip', '.tar', '.gz', '.sql', '.dump', '.bak', 'backup', 'admin', '.env', '.old'})"

time_list = timeit.timeit(test_list, setup=setup, number=1000000)
time_set = timeit.timeit(test_set, setup=setup, number=1000000)

print(f"Baseline (list): {time_list:.4f} seconds")
print(f"Optimized (set): {time_set:.4f} seconds")
print(f"Improvement: {(time_list - time_set) / time_list * 100:.2f}%")
