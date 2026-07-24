with open('tests/test_main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# I will add the test case to test_main.py, but first I need to mock httpx and others if it fails
# the test_main.py failed because httpx is not installed.
# Wait, if I just pip install httpx, will test_main.py pass?
