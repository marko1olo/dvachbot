import asyncio
import pytest

@pytest.fixture(scope="session", autouse=True)
<<<<<<< HEAD
def init_event_loop():
=======
def setup_event_loop():
>>>>>>> origin/main
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()
