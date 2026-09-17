import asyncio
from async_lru import alru_cache

@alru_cache(maxsize=10, ttl=60)
async def my_func():
    return 1

async def main():
    print(await my_func())

asyncio.run(main())
