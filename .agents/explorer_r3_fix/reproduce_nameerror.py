import sys
import os
import io

sys.path.insert(0, r"C:\Users\danat\Desktop\dvachbot")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import asyncio

async def test_call():
    import common.database as db
    print("Has db.db_sleep?", hasattr(db, 'db_sleep'))
    if not hasattr(db, 'db_sleep'):
        print("CONFIRMED BUG: common.database has NO attribute 'db_sleep'!")

if __name__ == "__main__":
    asyncio.run(test_call())
