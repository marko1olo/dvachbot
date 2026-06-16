from __future__ import annotations

import asyncio

import aiosqlite

from common.config import DB_NAME, DB_TIMEOUT
from common.database import initialize_database


async def foreign_key_violation_count() -> int:
    async with aiosqlite.connect(DB_NAME, timeout=DB_TIMEOUT) as db:
        await db.execute("PRAGMA foreign_keys = ON;")
        async with db.execute("PRAGMA foreign_key_check;") as cursor:
            rows = await cursor.fetchall()
    return len(rows)


async def main() -> int:
    await initialize_database()
    violation_count = await foreign_key_violation_count()
    print("foreign key violations:", violation_count)
    return 0 if violation_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
