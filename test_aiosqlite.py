import asyncio
import aiosqlite
import sqlite3

async def main():
    async with aiosqlite.connect("test.db") as con:
        await con.execute("CREATE TABLE IF NOT EXISTS T (id INTEGER)")
        await con.execute("INSERT INTO T VALUES (1)")
        await con.commit()

        cur = await con.execute("DELETE FROM T WHERE id=1")
        print("rowcount:", cur.rowcount)
        await con.commit()

asyncio.run(main())
