import asyncio
import aiosqlite

async def main():
    async with aiosqlite.connect(":memory:") as con:
        await con.execute("CREATE TABLE T (id INTEGER)")
        await con.execute("INSERT INTO T VALUES (1)")
        await con.commit()
        print("total_changes:", con.total_changes)

asyncio.run(main())
