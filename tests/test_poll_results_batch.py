import pytest
import asyncio
from common.database import get_poll_results_batch

@pytest.mark.asyncio
async def test_get_poll_results_batch(monkeypatch):
    import common.config
    common.config.DB_NAME = 'test_poll_batch.sqlite'

    from common.db_pool import get_pool, close_pool
    db = await get_pool()

    await db.execute("CREATE TABLE IF NOT EXISTS PollVotes (id INTEGER PRIMARY KEY, post_num INTEGER, option_index INTEGER)")
    await db.execute("DELETE FROM PollVotes")

    post_nums = [1, 2, 3]
    for pid in post_nums:
        for opt in range(2):
            for _ in range(pid):
                await db.execute("INSERT INTO PollVotes (post_num, option_index) VALUES (?, ?)", (pid, opt))
    await db.commit()

    results = await get_poll_results_batch(post_nums)

    assert results[1] == {"0": 1, "1": 1}
    assert results[2] == {"0": 2, "1": 2}
    assert results[3] == {"0": 3, "1": 3}

    # Empty case
    assert await get_poll_results_batch([]) == {}

    await close_pool()
