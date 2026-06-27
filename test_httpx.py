import asyncio
import httpx

async def main():
    transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
    async with httpx.AsyncClient(transport=transport) as client:
        print("created client")

asyncio.run(main())
