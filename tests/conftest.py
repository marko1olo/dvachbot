import asyncio
import pytest

@pytest.fixture(scope="session", autouse=True)
def init_event_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()
