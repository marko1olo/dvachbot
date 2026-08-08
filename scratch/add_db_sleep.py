import os

content = ""
with open('common/db_pool.py', 'r', encoding='utf-8') as f:
    content = f.read()

sleep_func = """
async def db_sleep(delay: float):
    \"\"\"Безопасный sleep для отпускания db_lock во время ожидания.\"\"\"
    lock_released = False
    if db_lock.locked():
        try:
            db_lock.release()
            lock_released = True
        except RuntimeError:
            pass
    try:
        await asyncio.sleep(delay)
    finally:
        if lock_released:
            await db_lock.acquire()
"""

if 'def db_sleep' not in content:
    content = content + '\n' + sleep_func
    with open('common/db_pool.py', 'w', encoding='utf-8') as f:
        f.write(content)

with open('common/database.py', 'r', encoding='utf-8') as f:
    db_content = f.read()

if 'from .db_pool import db_sleep' not in db_content:
    db_content = db_content.replace('from .db_pool import get_pool, create_pool, close_pool, db_lock', 'from .db_pool import get_pool, create_pool, close_pool, db_lock, db_sleep')
    db_content = db_content.replace('await asyncio.sleep(', 'await db_sleep(')
    with open('common/database.py', 'w', encoding='utf-8') as f:
        f.write(db_content)
    print("Patched database.py")
