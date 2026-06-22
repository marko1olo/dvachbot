import time

def benchmark():
    # Simulate a larger number of items to show the O(N) vs O(1) difference clearly
    num_tasks = 10000
    num_new_rows = 1000

    # Original implementation
    tasks1 = [{'fid': i, 'type': 'image'} for i in range(num_tasks)]
    rows1 = [(i, 'photo') for i in range(num_tasks - num_new_rows//2, num_tasks + num_new_rows//2)]

    start1 = time.time()
    for row in rows1:
        if not any(t['fid'] == row[0] for t in tasks1):
            tasks1.append({'fid': row[0], 'type': row[1], 'bot_id': None})
    end1 = time.time()
    time_orig = end1 - start1

    # Optimized implementation
    tasks2 = [{'fid': i, 'type': 'image'} for i in range(num_tasks)]
    rows2 = [(i, 'photo') for i in range(num_tasks - num_new_rows//2, num_tasks + num_new_rows//2)]

    start2 = time.time()
    task_fids = {t['fid'] for t in tasks2}
    for row in rows2:
        if row[0] not in task_fids:
            tasks2.append({'fid': row[0], 'type': row[1], 'bot_id': None})
            task_fids.add(row[0])
    end2 = time.time()
    time_opt = end2 - start2

    print(f"Original time: {time_orig:.6f}s")
    print(f"Optimized time: {time_opt:.6f}s")
    print(f"Improvement: {time_orig / time_opt if time_opt > 0 else float('inf'):.2f}x faster")

benchmark()
