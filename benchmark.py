import timeit

setup_code = """
ftype_image = 'sticker'
ftype_video = 'gif'
"""

list_test = """
_ = ftype_image in ['image', 'photo', 'sticker']
_ = ftype_video in ['video', 'animation', 'video_note', 'gif']
"""

set_test = """
_ = ftype_image in {'image', 'photo', 'sticker'}
_ = ftype_video in {'video', 'animation', 'video_note', 'gif'}
"""

n = 10000000

list_time = timeit.timeit(list_test, setup=setup_code, number=n)
set_time = timeit.timeit(set_test, setup=setup_code, number=n)

print(f"List lookup time: {list_time:.4f} seconds")
print(f"Set lookup time: {set_time:.4f} seconds")
print(f"Improvement: {(list_time - set_time) / list_time * 100:.2f}%")
