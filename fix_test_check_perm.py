import re

with open("tests/test_check_perm.py", "r", encoding="utf-8") as f:
    content = f.read()

# Make sure asyncio event loop is set up before importing Dubsite_tgach.main
new_content = """import asyncio
try:
    asyncio.get_running_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

""" + content

with open("tests/test_check_perm.py", "w", encoding="utf-8") as f:
    f.write(new_content)
