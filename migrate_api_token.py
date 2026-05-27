from __future__ import annotations

import asyncio

import aiosqlite

from common.config import DB_NAME, DB_TIMEOUT


async def column_exists(db: aiosqlite.Connection, table: str, column: str) -> bool:
    async with db.execute(f"PRAGMA table_info({table});") as cursor:
        rows = await cursor.fetchall()
    return any(row[1] == column for row in rows)


async def migrate_token_column() -> int:
    async with aiosqlite.connect(DB_NAME, timeout=DB_TIMEOUT, isolation_level=None) as db:
        await db.execute("PRAGMA busy_timeout = 30000;")
        await db.execute("PRAGMA foreign_keys = ON;")
        await db.execute("BEGIN IMMEDIATE;")
        try:
            if not await column_exists(db, "Users", "api_token"):
                await db.execute("ALTER TABLE Users ADD COLUMN api_token TEXT;")
                print("added Users.api_token")
            else:
                print("Users.api_token already exists")

            await db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_api_token "
                "ON Users(api_token) WHERE api_token IS NOT NULL;"
            )
            await db.commit()
            print("api_token migration complete:", DB_NAME)
            return 0
        except Exception:
            await db.rollback()
            raise


if __name__ == "__main__":
    raise SystemExit(asyncio.run(migrate_token_column()))
